"""
Conversation analyzer for Consigliere AI.

Analyzes chat conversations to extract insights, metrics, and patterns.
"""

import logging
from typing import Dict, List, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class ConversationAnalyzer:
    """
    Analyzes ChatGroup conversations to extract insights and metrics.
    """

    # Conversation type keywords
    CONVERSATION_TYPES = {
        "technical_discussion": [
            "code",
            "bug",
            "error",
            "function",
            "api",
            "implementation",
            "debug",
            "algorithm",
        ],
        "creative_writing": [
            "story",
            "write",
            "creative",
            "narrative",
            "character",
            "plot",
            "describe",
        ],
        "data_analysis": [
            "data",
            "analyze",
            "statistics",
            "trend",
            "chart",
            "report",
            "metrics",
        ],
        "general_assistance": [
            "help",
            "how",
            "what",
            "explain",
            "tell me",
            "why",
        ],
        "research": ["research", "find", "information", "learn", "study", "paper"],
        "brainstorming": [
            "ideas",
            "suggest",
            "brainstorm",
            "think",
            "possibilities",
        ],
    }

    def analyze_chat_group(
        self, chat_group_data: Dict[str, Any], user_preferences: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Analyze a ChatGroup and extract comprehensive insights.

        Args:
            chat_group_data: Full ChatGroup data from frontend
            user_preferences: Optional user preferences

        Returns:
            Dictionary containing analysis results
        """
        chats = chat_group_data.get("chats", [])

        if not chats:
            return self._empty_analysis()

        # Extract all messages
        all_messages = []
        for chat in chats:
            all_messages.extend(chat.get("messages", []))

        # Perform analysis
        conversation_type = self._detect_conversation_type(all_messages)
        metrics = self._calculate_metrics(all_messages)
        detected_needs = self._detect_needs(all_messages, metrics)
        insights = self._extract_insights(chats, metrics, conversation_type, detected_needs)
        models_used = self._get_models_used(all_messages)

        return {
            "conversation_type": conversation_type,
            "total_messages": metrics["total_messages"],
            "total_tokens": metrics["total_tokens"],
            "avg_cost_per_message": metrics["avg_cost_per_message"],
            "avg_latency": metrics["avg_latency"],
            "total_cost": metrics["total_cost"],
            "insights": insights,
            "detected_needs": detected_needs,
            "user_preferences": user_preferences or {},
            "models_used": models_used,
        }

    def _detect_conversation_type(self, messages: List[Dict[str, Any]]) -> str:
        """
        Detect the conversation type based on message content.

        Args:
            messages: List of messages

        Returns:
            Conversation type string
        """
        # Collect all user messages content
        user_messages = [
            msg.get("content", "").lower()
            for msg in messages
            if msg.get("role") == "user"
        ]

        if not user_messages:
            return "unknown"

        all_text = " ".join(user_messages)

        # Score each conversation type
        type_scores = {}
        for conv_type, keywords in self.CONVERSATION_TYPES.items():
            score = sum(1 for keyword in keywords if keyword in all_text)
            type_scores[conv_type] = score

        # Return type with highest score
        if max(type_scores.values()) == 0:
            return "general_assistance"

        return max(type_scores, key=type_scores.get)

    def _get_models_used(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract unique models used in conversation and their usage statistics.

        Args:
            messages: List of messages

        Returns:
            List of dictionaries with model usage data
        """
        models_used = {}

        for msg in messages:
            if msg.get("model_id") and msg.get("tokens"):
                model_id = msg["model_id"]
                if model_id not in models_used:
                    models_used[model_id] = {
                        "model_id": model_id,
                        "total_prompt_tokens": 0,
                        "total_completion_tokens": 0,
                        "total_cost": Decimal("0"),
                        "message_count": 0,
                    }

                models_used[model_id]["total_prompt_tokens"] += msg["tokens"].get("prompt", 0)
                models_used[model_id]["total_completion_tokens"] += msg["tokens"].get("completion", 0)
                models_used[model_id]["total_cost"] += Decimal(str(msg.get("cost", 0)))
                models_used[model_id]["message_count"] += 1

        return list(models_used.values())

    def _calculate_metrics(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate conversation metrics.

        Args:
            messages: List of messages

        Returns:
            Dictionary of metrics
        """
        total_messages = len(messages)

        # Cost metrics
        costs = [Decimal(str(msg.get("cost", 0))) for msg in messages if msg.get("cost")]
        total_cost = sum(costs) if costs else Decimal("0")
        avg_cost = total_cost / len(costs) if costs else Decimal("0")

        # Token metrics
        tokens = []
        for msg in messages:
            if msg.get("tokens"):
                tokens_data = msg["tokens"]
                tokens.append(
                    tokens_data.get("prompt", 0) + tokens_data.get("completion", 0)
                )
        total_tokens = sum(tokens) if tokens else 0

        # Latency metrics (convert from milliseconds to seconds)
        latencies = [
            float(msg.get("latency", 0)) / 1000.0 for msg in messages if msg.get("latency")
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "total_messages": total_messages,
            "total_cost": total_cost,
            "avg_cost_per_message": avg_cost,
            "total_tokens": total_tokens,
            "avg_latency": avg_latency,
        }

    def _extract_insights(
        self,
        chats: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        conversation_type: str,
        detected_needs: Dict[str, Any]
    ) -> List[str]:
        """
        Extract key insights from the conversation.

        Args:
            chats: List of Chat objects
            metrics: Calculated metrics
            conversation_type: Detected conversation type
            detected_needs: Detected user needs

        Returns:
            List of insight strings
        """
        insights = []

        # Always add conversation overview
        total_messages = metrics["total_messages"]
        num_chats = len(chats)
        insights.append(
            f"Analyzed {total_messages} message{'s' if total_messages != 1 else ''} across {num_chats} chat{'s' if num_chats != 1 else ''}"
        )

        # Add conversation type insight
        type_label = conversation_type.replace('_', ' ').title()
        insights.append(f"Conversation type: {type_label}")

        # Cost insights (only if cost data is available)
        avg_cost = float(metrics["avg_cost_per_message"])
        if avg_cost > 0.01:
            insights.append(
                f"High cost per message (${avg_cost:.4f}) - consider cost optimization"
            )
        elif avg_cost > 0:
            insights.append(
                f"Moderate cost per message (${avg_cost:.4f}) - good balance"
            )

        # Latency insights (only if latency data is available)
        avg_latency = metrics["avg_latency"]
        if avg_latency > 5.0:
            insights.append(
                f"High latency ({avg_latency:.1f}s) - consider faster models"
            )
        elif avg_latency > 2.0:
            insights.append(
                f"Moderate latency ({avg_latency:.1f}s) - acceptable for most uses"
            )
        elif avg_latency > 0:
            insights.append(
                f"Good latency ({avg_latency:.1f}s) - fast responses"
            )

        # Multi-model insights
        if len(chats) > 1:
            insights.append(
                f"Using {len(chats)} models concurrently - comparing performance"
            )

        # Attachment insights (from lightweight attachments_meta): images / PDFs / other files
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
            insights.append("Attachments used: " + ", ".join(parts))

        # Message length insights
        all_messages = []
        for chat in chats:
            all_messages.extend(chat.get("messages", []))

        user_msgs = [m for m in all_messages if m.get("role") == "user"]
        if user_msgs:
            avg_user_len = sum(len(m.get("content", "")) for m in user_msgs) / len(
                user_msgs
            )
            if avg_user_len > 500:
                insights.append(
                    "Long user queries - models with larger context may be beneficial"
                )

        assistant_msgs = [m for m in all_messages if m.get("role") == "assistant"]
        if assistant_msgs:
            avg_assistant_len = sum(
                len(m.get("content", "")) for m in assistant_msgs
            ) / len(assistant_msgs)
            if avg_assistant_len < 100:
                insights.append(
                    "Short responses - consider models optimized for concise answers"
                )

        # Add insights based on detected needs
        if detected_needs:
            if detected_needs.get("creativity"):
                insights.append(f"Creativity focus: {detected_needs['creativity']}")
            if detected_needs.get("precision"):
                insights.append(f"Precision focus: {detected_needs['precision']}")
            if detected_needs.get("speed"):
                insights.append(f"Speed focus: {detected_needs['speed']}")
            if detected_needs.get("cost_efficiency"):
                insights.append(f"Cost focus: {detected_needs['cost_efficiency']}")

        return insights[:8]  # Return top 8 insights (increased from 5)

    def _detect_needs(
        self, messages: List[Dict[str, Any]], metrics: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Detect user needs based on conversation patterns.

        Args:
            messages: List of messages
            metrics: Calculated metrics

        Returns:
            Dictionary of detected needs (creativity, precision, speed, cost)
        """
        needs = {}

        # Analyze user messages for needs indicators
        user_messages = [
            msg.get("content", "").lower()
            for msg in messages
            if msg.get("role") == "user"
        ]
        all_user_text = " ".join(user_messages)

        # Creativity need
        creativity_keywords = [
            "creative",
            "innovative",
            "unique",
            "original",
            "imagine",
            "design",
        ]
        creativity_score = sum(
            1 for kw in creativity_keywords if kw in all_user_text
        )
        needs["creativity"] = (
            "high" if creativity_score >= 2 else "medium" if creativity_score >= 1 else "low"
        )

        # Precision need
        precision_keywords = [
            "accurate",
            "precise",
            "exact",
            "correct",
            "specific",
            "detailed",
        ]
        precision_score = sum(1 for kw in precision_keywords if kw in all_user_text)
        needs["precision"] = (
            "high" if precision_score >= 2 else "medium" if precision_score >= 1 else "low"
        )

        # Speed need (based on latency tolerance)
        avg_latency = metrics["avg_latency"]
        needs["speed"] = (
            "high" if avg_latency < 2.0 else "medium" if avg_latency < 5.0 else "low"
        )

        # Cost sensitivity (based on current spending)
        avg_cost = float(metrics["avg_cost_per_message"])
        needs["cost_efficiency"] = (
            "high" if avg_cost > 0.01 else "medium" if avg_cost > 0.003 else "low"
        )

        return needs

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "conversation_type": "unknown",
            "total_messages": 0,
            "total_tokens": 0,
            "avg_cost_per_message": Decimal("0"),
            "avg_latency": 0.0,
            "total_cost": Decimal("0"),
            "insights": ["No conversation data available"],
            "detected_needs": {},
            "user_preferences": {},
        }
