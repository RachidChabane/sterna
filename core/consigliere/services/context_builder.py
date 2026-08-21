"""
Context builder for Consigliere AI.

Constructs rich context from conversation data to provide to the LLM.
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal

from ..config import ContextConfig

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Builds context strings from conversation data for Consigliere prompts.
    """

    def build_context(
        self,
        chat_group: Dict[str, Any],
        analysis: Optional[Dict[str, Any]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build a comprehensive context string from conversation data.

        Args:
            chat_group: ChatGroup data from frontend
            analysis: Optional analysis results
            user_preferences: Optional user preferences

        Returns:
            Formatted context string for LLM prompts
        """
        context_parts = []

        # 1. Conversation content (MOST IMPORTANT - shown first)
        content = self._build_conversation_content(chat_group)
        context_parts.append(f"**Conversation Content:**\n{content}")

        # 2. Conversation summary
        summary = self._build_conversation_summary(chat_group)
        context_parts.append(f"\n**Conversation Summary:**\n{summary}")

        # 3. Analysis results (if available)
        if analysis:
            analysis_text = self._build_analysis_context(analysis)
            context_parts.append(f"\n**Analysis Results:**\n{analysis_text}")

        # 4. User preferences (if available)
        if user_preferences:
            prefs_text = self._build_preferences_context(user_preferences)
            context_parts.append(f"\n**User Preferences:**\n{prefs_text}")

        # 5. Current state
        state_text = self._build_state_context(chat_group)
        context_parts.append(f"\n**Current State:**\n{state_text}")

        return "\n".join(context_parts)

    def _build_conversation_content(self, chat_group: Dict[str, Any]) -> str:
        """
        Build formatted conversation content showing actual messages.

        Args:
            chat_group: ChatGroup data

        Returns:
            Formatted conversation content with messages
        """
        chats = chat_group.get("chats", [])

        if not chats:
            return "No conversation messages available."

        content_lines = []
        max_messages_per_chat = ContextConfig.MAX_MESSAGES_PER_CHAT
        max_message_length = ContextConfig.MAX_MESSAGE_LENGTH

        # Conversation-level attachments summary first
        total_images = 0
        total_pdfs = 0
        total_files = 0
        for chat in chats:
            for m in chat.get("messages", []):
                for att in m.get("attachments_meta", []) or []:
                    if att.get("type") == "image":
                        total_images += 1
                    elif att.get("type") == "file":
                        if att.get("is_pdf"):
                            total_pdfs += 1
                        else:
                            total_files += 1

        if total_images or total_pdfs or total_files:
            parts = []
            if total_images:
                parts.append(f"{total_images} image{'s' if total_images != 1 else ''}")
            if total_pdfs:
                parts.append(f"{total_pdfs} PDF{'s' if total_pdfs != 1 else ''}")
            if total_files:
                parts.append(f"{total_files} file{'s' if total_files != 1 else ''}")
            content_lines.append(
                f"[Attachment Summary] Conversation included: {', '.join(parts)}"
            )
            content_lines.append("")

        for chat_idx, chat in enumerate(chats):
            messages = chat.get("messages", [])
            if not messages:
                continue

            model_name = chat.get("model", {}).get("name", "Unknown Model")
            content_lines.append(f"\n[Chat {chat_idx + 1} - {model_name}]")

            # Take recent messages (last N messages)
            recent_messages = messages[-max_messages_per_chat:]

            for msg in recent_messages:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")

                # Truncate long messages
                if len(content) > max_message_length:
                    content = content[:max_message_length] + "... [truncated]"

                content_lines.append(f"{role}: {content}")

                # If this message carried attachments, add a short note with filenames
                attachments_meta = msg.get("attachments_meta") or []
                if attachments_meta:
                    images = [a for a in attachments_meta if a.get("type") == "image"]
                    pdfs = [a for a in attachments_meta if a.get("type") == "file" and a.get("is_pdf")]
                    other_files = [a for a in attachments_meta if a.get("type") == "file" and not a.get("is_pdf")]

                    parts = []

                    # Images with filenames
                    if images:
                        img_names = [a.get("filename") for a in images[:3] if a.get("filename")]
                        if img_names:
                            parts.append(f"{len(images)} image{'s' if len(images) != 1 else ''} ({', '.join(img_names)})")
                        else:
                            parts.append(f"{len(images)} image{'s' if len(images) != 1 else ''}")

                    # PDFs with filenames
                    if pdfs:
                        pdf_names = [a.get("filename") for a in pdfs[:3] if a.get("filename")]
                        if pdf_names:
                            parts.append(f"{len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''} ({', '.join(pdf_names)})")
                        else:
                            parts.append(f"{len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}")

                    # Other files with filenames
                    if other_files:
                        file_names = [a.get("filename") for a in other_files[:3] if a.get("filename")]
                        if file_names:
                            parts.append(f"{len(other_files)} file{'s' if len(other_files) != 1 else ''} ({', '.join(file_names)})")
                        else:
                            parts.append(f"{len(other_files)} file{'s' if len(other_files) != 1 else ''}")

                    content_lines.append(f"  ↳ Attachments: {', '.join(parts)}")

            # Add separator between chats
            if chat_idx < len(chats) - 1:
                content_lines.append("")

        return "\n".join(content_lines) if content_lines else "No messages found."

    def _build_conversation_summary(self, chat_group: Dict[str, Any]) -> str:
        """Build a summary of the conversation."""
        chats = chat_group.get("chats", [])

        if not chats:
            return "No conversation data available."

        # Count messages across all chats
        total_messages = sum(len(chat.get("messages", [])) for chat in chats)

        # Extract unique models
        models_used = set()
        for chat in chats:
            if chat.get("model"):
                models_used.add(chat["model"].get("name", "Unknown"))

        # Calculate total cost (if available)
        total_cost = Decimal("0")
        for chat in chats:
            for message in chat.get("messages", []):
                if message.get("cost"):
                    total_cost += Decimal(str(message.get("cost", 0)))

        # Calculate average latency (convert from milliseconds to seconds)
        latencies = []
        for chat in chats:
            for message in chat.get("messages", []):
                if message.get("latency"):
                    latencies.append(float(message.get("latency", 0)) / 1000.0)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Build summary
        summary_lines = [
            f"- Total messages: {total_messages}",
            f"- Models in use: {', '.join(sorted(models_used)) if models_used else 'None'}",
            f"- Total cost: ${float(total_cost):.4f}",
            f"- Average latency: {avg_latency:.2f}s",
        ]

        return "\n".join(summary_lines)

    def _build_analysis_context(self, analysis: Dict[str, Any]) -> str:
        """Build context from analysis results."""
        lines = []

        # Conversation type
        if analysis.get("conversation_type"):
            lines.append(f"- Type: {analysis['conversation_type']}")

        # Insights
        if analysis.get("insights"):
            insights_text = "\n  • " + "\n  • ".join(analysis["insights"])
            lines.append(f"- Key Insights:{insights_text}")

        # Detected needs
        if analysis.get("detected_needs"):
            needs = analysis["detected_needs"]
            needs_text = ", ".join(f"{k}: {v}" for k, v in needs.items())
            lines.append(f"- Detected Needs: {needs_text}")

        # Metrics
        if analysis.get("total_tokens"):
            lines.append(f"- Total tokens: {analysis['total_tokens']:,}")

        if analysis.get("avg_cost_per_message"):
            lines.append(
                f"- Avg cost/message: ${float(analysis['avg_cost_per_message']):.4f}"
            )

        return "\n".join(lines) if lines else "No analysis available."

    def _build_preferences_context(self, user_preferences: Dict[str, Any]) -> str:
        """Build context from user preferences."""
        if not user_preferences:
            return "No user preferences specified."

        prefs = []

        if user_preferences.get("budget_preference"):
            prefs.append(f"- Budget: {user_preferences['budget_preference']}")

        if user_preferences.get("priority"):
            prefs.append(f"- Priority: {user_preferences['priority']}")

        if user_preferences.get("max_cost_per_message"):
            prefs.append(
                f"- Max cost/message: ${user_preferences['max_cost_per_message']}"
            )

        return "\n".join(prefs) if prefs else "No specific preferences."

    def _build_state_context(self, chat_group: Dict[str, Any]) -> str:
        """Build context about current conversation state."""
        chats = chat_group.get("chats", [])

        lines = []

        # Number of concurrent chats
        lines.append(f"- Number of active chats: {len(chats)}")

        # Latest messages
        latest_messages = []
        for i, chat in enumerate(chats):
            messages = chat.get("messages", [])
            if messages:
                last_msg = messages[-1]
                model_name = chat.get("model", {}).get("name", "Unknown")
                latest_messages.append(
                    f"  Chat {i+1} ({model_name}): \"{last_msg.get('content', '')[:60]}...\""
                )

        if latest_messages:
            lines.append("- Latest messages:")
            lines.extend(latest_messages[:3])  # Show max 3

        return "\n".join(lines)

    def build_message_patterns_text(self, chat_group: Dict[str, Any]) -> str:
        """
        Extract and format message patterns from conversation.

        Args:
            chat_group: ChatGroup data

        Returns:
            Formatted text describing message patterns
        """
        chats = chat_group.get("chats", [])
        patterns = []

        for chat in chats:
            messages = chat.get("messages", [])
            if not messages:
                continue

            model_name = chat.get("model", {}).get("name", "Unknown")

            # Message length pattern
            user_msgs = [m for m in messages if m.get("role") == "user"]
            assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

            if user_msgs:
                avg_user_len = sum(
                    len(m.get("content", "")) for m in user_msgs
                ) / len(user_msgs)
                patterns.append(f"- {model_name} receives avg {avg_user_len:.0f} char queries")

            if assistant_msgs:
                avg_assistant_len = sum(
                    len(m.get("content", "")) for m in assistant_msgs
                ) / len(assistant_msgs)
                patterns.append(
                    f"- {model_name} responds with avg {avg_assistant_len:.0f} char answers"
                )

        return "\n".join(patterns) if patterns else "No clear patterns detected."
