"""
Conversation Summarization

Summarizes older job conversations to reduce token usage while preserving context.
Uses a cheap model to generate concise summaries.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .constants import (
    BATCH_SUMMARY_MAX_TOKENS,
    SCOUT_MODEL_ID,
    SUMMARIZATION_TEMPERATURE,
    SUMMARY_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """Summarizes job conversations to reduce context size."""

    def __init__(self, model_id: Optional[str] = None, user=None):
        """
        Initialize summarizer.

        Args:
            model_id: Model to use for summarization (defaults to scout model)
            user: User instance for API key resolution
        """
        self.model_id = model_id or SCOUT_MODEL_ID
        self.user = user
        self._client = None

    @property
    def client(self):
        """Lazy-load the OpenRouter client."""
        if self._client is None:
            from llm.client import OpenRouterClient
            self._client = OpenRouterClient(user=self.user, request_source='summarizer')
        return self._client

    def summarize_job(self, job: Any) -> str:
        """
        Summarize a single job's conversation.

        Args:
            job: CodeJob instance

        Returns:
            Concise summary string (target: 100-200 tokens)
        """
        # Extract key information from job
        prompt = job.prompt[:500] if job.prompt else "Unknown task"
        files_modified = job.files_modified or []
        status = job.status

        # Build context from steps if available
        actions_taken = []
        if job.steps:
            for step in job.steps:
                if step.get("type") == "text" and step.get("content"):
                    # Extract first sentence of each text response
                    content = step["content"]
                    first_sentence = content.split(".")[0][:100]
                    if first_sentence:
                        actions_taken.append(first_sentence)
                elif step.get("type") == "tool_executions":
                    for exec in step.get("executions", []):
                        tool_name = exec.get("tool_name", "")
                        if tool_name in ("write_file", "edit_file"):
                            args = exec.get("arguments", {})
                            path = args.get("path", "unknown")
                            actions_taken.append(f"Modified {path}")
                        elif tool_name == "run_bash":
                            args = exec.get("arguments", {})
                            cmd = args.get("command", "")[:50]
                            actions_taken.append(f"Ran: {cmd}")

        # If we have enough local info, skip LLM call
        if files_modified or actions_taken:
            return self._build_local_summary(
                prompt, status, files_modified, actions_taken
            )

        # Use LLM for complex summarization
        return self._llm_summarize_job(job)

    def _build_local_summary(
        self,
        prompt: str,
        status: str,
        files_modified: List[str],
        actions_taken: List[str]
    ) -> str:
        """Build a summary without LLM call when we have enough info."""
        parts = []

        # Task (truncated)
        task_summary = prompt[:100] + "..." if len(prompt) > 100 else prompt
        parts.append(f"Task: {task_summary}")

        # Status
        if status == "completed":
            parts.append("Status: Completed successfully")
        elif status == "failed":
            parts.append("Status: Failed")
        else:
            parts.append(f"Status: {status}")

        # Files modified
        if files_modified:
            if len(files_modified) <= 3:
                parts.append(f"Modified: {', '.join(files_modified)}")
            else:
                parts.append(
                    f"Modified {len(files_modified)} files: "
                    f"{', '.join(files_modified[:3])}..."
                )

        # Key actions (first 3)
        if actions_taken:
            unique_actions = list(dict.fromkeys(actions_taken))[:3]
            parts.append(f"Actions: {'; '.join(unique_actions)}")

        return " | ".join(parts)

    def _llm_summarize_job(self, job: Any) -> str:
        """Use LLM to summarize a complex job."""
        try:
            # Build context
            context = {
                "prompt": job.prompt[:500] if job.prompt else "",
                "status": job.status,
                "files_modified": job.files_modified or [],
            }

            # Extract text content from steps
            text_content = []
            if job.steps:
                for step in job.steps:
                    if step.get("type") == "text" and step.get("content"):
                        text_content.append(step["content"][:300])

            context["responses"] = text_content[:3]

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Summarize this coding job in 1-2 sentences. "
                        "Include: what was done, files changed, outcome. "
                        "Be concise. Output ONLY the summary, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                },
            ]

            result = self.client.complete(
                model=self.model_id,
                messages=messages,
                max_tokens=SUMMARY_MAX_TOKENS,
                temperature=SUMMARIZATION_TEMPERATURE,
            )

            summary = result.get("content", "").strip()
            if summary:
                logger.debug(f"LLM summary for job {job.id}: {summary[:100]}...")
                return summary

        except Exception as e:
            logger.warning(f"LLM summarization failed for job {job.id}: {e}")

        # Fallback to local summary
        return self._build_local_summary(
            job.prompt or "",
            job.status,
            job.files_modified or [],
            []
        )

    def summarize_jobs_batch(self, jobs: List[Any]) -> str:
        """
        Summarize multiple jobs into a single context block.

        Args:
            jobs: List of CodeJob instances to summarize

        Returns:
            Combined summary string
        """
        if not jobs:
            return ""

        # For small batches, summarize individually and combine
        if len(jobs) <= 3:
            summaries = []
            for i, job in enumerate(jobs, 1):
                summary = self.summarize_job(job)
                summaries.append(f"{i}. {summary}")
            return "\n".join(summaries)

        # For larger batches, use LLM to create a cohesive summary
        try:
            job_summaries = []
            for job in jobs:
                job_summaries.append({
                    "prompt": job.prompt[:200] if job.prompt else "",
                    "status": job.status,
                    "files": job.files_modified[:5] if job.files_modified else [],
                })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Summarize these coding jobs as a cohesive work history. "
                        "Highlight: overall progress, key files changed, "
                        "current state of the work. Be concise (3-4 sentences max). "
                        "Output ONLY the summary."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(job_summaries, ensure_ascii=False),
                },
            ]

            result = self.client.complete(
                model=self.model_id,
                messages=messages,
                max_tokens=BATCH_SUMMARY_MAX_TOKENS,
                temperature=SUMMARIZATION_TEMPERATURE,
            )

            summary = result.get("content", "").strip()
            if summary:
                return f"Previous work ({len(jobs)} jobs): {summary}"

        except Exception as e:
            logger.warning(f"Batch summarization failed: {e}")

        # Fallback: individual summaries (truncated)
        summaries = []
        for job in jobs[:5]:  # Limit fallback
            summaries.append(self._build_local_summary(
                job.prompt or "",
                job.status,
                job.files_modified or [],
                []
            ))

        combined = " | ".join(summaries)
        if len(jobs) > 5:
            combined += f" | ... and {len(jobs) - 5} more jobs"

        return combined

    def estimate_token_savings(
        self,
        jobs: List[Any],
        original_context_tokens: int
    ) -> Dict[str, Any]:
        """
        Estimate token savings from summarization.

        Args:
            jobs: Jobs that would be summarized
            original_context_tokens: Tokens if full context was used

        Returns:
            Dict with savings metrics
        """
        # Estimate summary tokens (rough: 50-100 tokens per job summary)
        estimated_summary_tokens = len(jobs) * 75

        # Add batch overhead if using batch summary
        if len(jobs) > 3:
            estimated_summary_tokens = min(
                estimated_summary_tokens,
                BATCH_SUMMARY_MAX_TOKENS + 100  # Prompt overhead
            )

        savings = original_context_tokens - estimated_summary_tokens
        savings_pct = savings / original_context_tokens if original_context_tokens > 0 else 0

        return {
            "original_tokens": original_context_tokens,
            "summarized_tokens": estimated_summary_tokens,
            "tokens_saved": savings,
            "savings_percentage": savings_pct,
            "jobs_summarized": len(jobs),
        }


# Singleton instance
_summarizer_instance: Optional[ConversationSummarizer] = None


def get_summarizer() -> ConversationSummarizer:
    """Get or create the singleton summarizer instance."""
    global _summarizer_instance
    if _summarizer_instance is None:
        _summarizer_instance = ConversationSummarizer()
    return _summarizer_instance


def summarize_conversation_history(
    jobs: List[Any],
    max_full_jobs: int = 2,
    user=None
) -> Dict[str, Any]:
    """
    Summarize conversation history, keeping recent jobs in full.

    Args:
        jobs: List of previous CodeJob instances (ordered by created_at)
        max_full_jobs: Number of recent jobs to keep in full
        user: User instance for API key resolution

    Returns:
        Dict with:
            - summary: Optional summary of older jobs
            - recent_jobs: List of jobs to include in full
            - metrics: Token savings metrics
    """
    logger.info(f"[Summarizer] Processing {len(jobs)} previous jobs (max_full={max_full_jobs})")

    if len(jobs) <= max_full_jobs:
        logger.info(f"[Summarizer] No summarization needed, {len(jobs)} jobs <= {max_full_jobs}")
        return {
            "summary": None,
            "recent_jobs": jobs,
            "metrics": {"jobs_summarized": 0},
        }

    # Split into older (to summarize) and recent (keep full)
    older_jobs = jobs[:-max_full_jobs]
    recent_jobs = jobs[-max_full_jobs:]

    logger.info(f"[Summarizer] Summarizing {len(older_jobs)} older jobs, keeping {len(recent_jobs)} in full")

    summarizer = ConversationSummarizer(user=user)
    summary = summarizer.summarize_jobs_batch(older_jobs)

    logger.info(f"[Summarizer] Generated summary: {len(summary)} chars")
    logger.debug(f"[Summarizer] Summary content: {summary[:300]}...")

    return {
        "summary": summary,
        "recent_jobs": recent_jobs,
        "metrics": {
            "jobs_summarized": len(older_jobs),
            "summary_length": len(summary),
        },
    }
