"""
Plan Service — parse plan markdown and persist via ORM.

Runs inside the Django web process, so uses ORM directly (not HTTP).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from django.utils.text import slugify

from code_sessions.models import AgentPlan, ClonedRepository, PlanStep

logger = logging.getLogger(__name__)


@dataclass
class ParsedStep:
    title: str
    description: str
    files: List[str] = field(default_factory=list)


@dataclass
class ParsedPlan:
    title: str
    summary: str
    steps: List[ParsedStep]
    raw_content: str


def parse_plan_markdown(content: str) -> ParsedPlan:
    """Parse implementation plan markdown into structured data."""
    title = _extract_title(content)
    summary = _extract_summary(content)
    steps = _extract_steps(content)
    return ParsedPlan(title=title, summary=summary, steps=steps, raw_content=content)


def _extract_title(content: str) -> str:
    # Try multiple title formats:
    # 1. "# Implementation Plan: Title"
    # 2. "# Title" (any h1)
    match = re.search(r"^#\s+Implementation Plan:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_summary(content: str) -> str:
    match = re.search(r"##\s+Summary\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_steps(content: str) -> List[ParsedStep]:
    steps = []
    # Try multiple heading patterns that agents commonly produce:
    # 1. "### Step 1: Title"  (our requested format)
    # 2. "### 1. Title"       (numbered h3)
    # 3. "**Step 1: Title**"  (bold inline)
    patterns = [
        r"###\s+Step\s+\d+[:.]\s*(.+?)\n(.*?)(?=###\s+Step|\n##|\Z)",
        r"###\s+\d+\.\s*(.+?)\n(.*?)(?=###\s+\d+\.|\n##|\Z)",
        r"\*\*Step\s+\d+[:.]\s*(.+?)\*\*\n(.*?)(?=\*\*Step\s+\d+|\n##|\Z)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.DOTALL):
            title = match.group(1).strip()
            body = match.group(2).strip()
            files = _extract_files(body)
            description = re.sub(r"\*\*Files:\*\*.*?(?:\n|$)", "", body).strip()
            steps.append(ParsedStep(title=title, description=description, files=files))
        if steps:
            break  # Use the first pattern that matches
    return steps


def _extract_files(text: str) -> List[str]:
    match = re.search(r"\*\*Files:\*\*\s*(.+?)(?:\n|$)", text)
    if match:
        return [f.strip() for f in match.group(1).split(",")]
    return []


def create_plan_from_content(
    plan_content: str,
    conversation,
    task_description: str,
    issue_number: Optional[int] = None,
    issue_url: str = "",
    issue_title: str = "",
    chat=None,
) -> AgentPlan:
    """Parse plan markdown and create AgentPlan + PlanStep records.

    Returns the created AgentPlan instance.
    """
    parsed = parse_plan_markdown(plan_content)

    # Build title with fallback
    if parsed.title:
        title = parsed.title
    elif issue_number:
        title = f"Plan for issue #{issue_number}"
    else:
        title = "Implementation Plan"

    if not parsed.steps:
        logger.warning("Plan parsed with 0 steps — saving raw content anyway")

    # Resolve repo_full_name from conversation's cloned repository
    repo_full_name = ""
    try:
        repo_full_name = conversation.cloned_repository.full_name
    except ClonedRepository.DoesNotExist:
        pass

    plan = AgentPlan.objects.create(
        conversation=conversation,
        repo_full_name=repo_full_name,
        title=title,
        slug=slugify(title)[:100],
        task_description=task_description,
        plan_content=parsed.raw_content,
        total_steps=len(parsed.steps),
        status=AgentPlan.Status.READY if parsed.steps else AgentPlan.Status.CREATING,
        github_issue_number=issue_number,
        github_issue_url=issue_url,
        github_issue_title=issue_title,
        chat=chat,
    )

    for i, step in enumerate(parsed.steps, 1):
        PlanStep.objects.create(
            plan=plan,
            step_number=i,
            title=step.title,
            description=step.description,
            files_to_modify=step.files,
        )

    return plan


def import_plan(source_plan: AgentPlan, target_chat) -> AgentPlan:
    """Copy a plan into a different chat.

    Creates a new AgentPlan (and PlanStep copies) linked to target_chat,
    with source_plan set for lineage tracking.
    """
    new_plan = AgentPlan.objects.create(
        conversation=target_chat.conversation,
        chat=target_chat,
        source_plan=source_plan,
        repo_full_name=source_plan.repo_full_name,
        title=source_plan.title,
        slug=source_plan.slug,
        task_description=source_plan.task_description,
        plan_content=source_plan.plan_content,
        total_steps=source_plan.total_steps,
        status=AgentPlan.Status.READY,
        current_step_index=0,
        github_issue_number=source_plan.github_issue_number,
        github_issue_url=source_plan.github_issue_url,
        github_issue_title=source_plan.github_issue_title,
    )

    for step in source_plan.steps.all().order_by("step_number"):
        PlanStep.objects.create(
            plan=new_plan,
            step_number=step.step_number,
            title=step.title,
            description=step.description,
            files_to_modify=step.files_to_modify,
            status=PlanStep.Status.PENDING,
        )

    return new_plan


def update_plan_from_content(plan: AgentPlan, new_content: str) -> AgentPlan:
    """Re-parse plan markdown and update existing AgentPlan + PlanStep records.

    Deletes old steps and creates new ones from the updated content.
    Same parse logic as creation, applied to an existing plan.
    """
    parsed = parse_plan_markdown(new_content)

    # Update plan fields
    if parsed.title:
        plan.title = parsed.title
        plan.slug = slugify(parsed.title)[:100]
    plan.plan_content = parsed.raw_content
    plan.total_steps = len(parsed.steps)
    plan.current_step_index = 0

    if not parsed.steps:
        logger.warning("Updated plan parsed with 0 steps")

    # Keep status as ready if it had steps, otherwise creating
    if parsed.steps and plan.status in (AgentPlan.Status.CREATING, AgentPlan.Status.READY):
        plan.status = AgentPlan.Status.READY

    plan.save(update_fields=[
        "title", "slug", "plan_content", "total_steps",
        "current_step_index", "status", "updated_at",
    ])

    # Replace all steps: delete old, create new
    plan.steps.all().delete()

    for i, step in enumerate(parsed.steps, 1):
        PlanStep.objects.create(
            plan=plan,
            step_number=i,
            title=step.title,
            description=step.description,
            files_to_modify=step.files,
        )

    return plan
