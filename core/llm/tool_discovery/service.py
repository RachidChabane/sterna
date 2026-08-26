"""
Tool Discovery Service

Implements on-demand tool discovery following Anthropic's Tool Search Tool pattern.
Provides intelligent tool search with relevance scoring.
"""

import logging
import re
from typing import List, Optional, Dict, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
import threading

from ..tool_catalog.models import (
    ToolDefinition,
    ToolCategory,
    DiscoveredTool,
    FEATURE_FLAG_DISPLAY_NAMES,
)
from ..tool_catalog.registry import ToolCatalogRegistry, get_tool_catalog

logger = logging.getLogger(__name__)


@dataclass
class ToolDiscoveryContext:
    """
    Context for tool discovery within a session.

    Maintains state about:
    - User and conversation identity
    - Enabled features
    - Tools discovered during the session
    - Available MCP servers
    """

    user_id: str
    conversation_id: str
    chat_id: Optional[str] = None

    # Enabled features for this session
    enabled_features: Set[str] = field(default_factory=set)

    # Tools discovered in this session (cached for reuse)
    discovered_tool_ids: Set[str] = field(default_factory=set)

    # Available MCP servers for this user
    available_mcp_servers: List[str] = field(default_factory=list)

    # Session metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_search_at: Optional[datetime] = None
    total_searches: int = 0

    def add_discovered_tool(self, tool_id: str):
        """Mark a tool as discovered in this session."""
        self.discovered_tool_ids.add(tool_id)

    def is_tool_discovered(self, tool_id: str) -> bool:
        """Check if a tool was already discovered."""
        return tool_id in self.discovered_tool_ids

    def record_search(self):
        """Record that a search was performed."""
        self.last_search_at = datetime.utcnow()
        self.total_searches += 1


class ToolDiscoveryService:
    """
    Service for on-demand tool discovery.

    Implements Anthropic's Tool Search Tool pattern:
    - Tools are marked with loading_strategy (ALWAYS vs ON_DEMAND)
    - ON_DEMAND tools are discovered via search
    - Discovered tools are cached per session
    - Relevance scoring helps the LLM find the right tools
    """

    def __init__(self, catalog: Optional[ToolCatalogRegistry] = None):
        """
        Initialize the discovery service.

        Args:
            catalog: Tool catalog registry (uses global if not provided)
        """
        self.catalog = catalog or get_tool_catalog()
        self._session_contexts: Dict[str, ToolDiscoveryContext] = {}
        self._contexts_lock = threading.RLock()

        # Search configuration
        self._min_relevance_threshold = 0.1
        self._default_max_results = 20

        logger.info("[ToolDiscovery] Service initialized")

    def _make_context_key(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None
    ) -> str:
        """Generate a unique key for a context."""
        if chat_id:
            return f"{user_id}:{conversation_id}:{chat_id}"
        return f"{user_id}:{conversation_id}"

    def get_or_create_context(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None,
        enabled_features: Optional[Set[str]] = None
    ) -> ToolDiscoveryContext:
        """
        Get or create a discovery context for a session.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            chat_id: Optional chat identifier
            enabled_features: Set of enabled feature flags

        Returns:
            ToolDiscoveryContext for the session
        """
        context_key = self._make_context_key(user_id, conversation_id, chat_id)

        with self._contexts_lock:
            if context_key not in self._session_contexts:
                context = ToolDiscoveryContext(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    chat_id=chat_id,
                    enabled_features=enabled_features or set(),
                    available_mcp_servers=self._get_user_mcp_servers(user_id),
                )
                self._session_contexts[context_key] = context
                logger.info(f"[ToolDiscovery] Created context for {context_key}")
            else:
                # Update enabled features if provided
                context = self._session_contexts[context_key]
                if enabled_features:
                    context.enabled_features = enabled_features

            return self._session_contexts[context_key]

    def clear_context(
        self,
        user_id: str,
        conversation_id: str,
        chat_id: Optional[str] = None
    ):
        """Clear a session context."""
        context_key = self._make_context_key(user_id, conversation_id, chat_id)

        with self._contexts_lock:
            if context_key in self._session_contexts:
                del self._session_contexts[context_key]
                logger.info(f"[ToolDiscovery] Cleared context for {context_key}")

    def _get_user_mcp_servers(self, user_id: str) -> List[str]:
        """
        Get available MCP servers for a user.

        TODO: Query user-preferences service for configured MCP servers.
        """
        # Placeholder - will be implemented when MCP V2 is ready
        return []

    def search_tools(
        self,
        query: str,
        context: ToolDiscoveryContext,
        max_results: Optional[int] = None,
        category_filter: Optional[ToolCategory] = None
    ) -> List[DiscoveredTool]:
        """
        Search for tools matching a query.

        Implements intelligent relevance scoring based on:
        - Name matching
        - Description matching
        - Keyword matching
        - Tag matching
        - Usage frequency

        Note: Returns ALL matching tools regardless of enabled features,
        but marks tools as disabled if their required feature isn't enabled.
        This allows users to discover available capabilities.

        Args:
            query: Search query
            context: Discovery context
            max_results: Maximum results to return
            category_filter: Optional category filter

        Returns:
            List of discovered tools with relevance scores
        """
        max_results = max_results or self._default_max_results
        context.record_search()

        # Get ALL tools (not filtered by features) so users can discover capabilities
        # Include user-specific tools (e.g., MCP tools) by passing user_id
        all_tools = self.catalog.get_all_searchable_tools(user_id=context.user_id)

        # Debug: log tool count and check for specific tools
        notion_tools = [t for t in all_tools if 'notion' in t.id.lower()]
        logger.info(f"[ToolDiscovery] Total tools: {len(all_tools)}, Notion tools: {len(notion_tools)}")
        for t in notion_tools:
            logger.debug(f"[ToolDiscovery] Notion tool: {t.id} (category={t.category})")

        # Filter by category if specified
        if category_filter:
            before_count = len(all_tools)
            all_tools = [
                t for t in all_tools
                if t.category == category_filter
            ]
            logger.info(f"[ToolDiscovery] Category filter '{category_filter.value}': {before_count} -> {len(all_tools)} tools")

        # Score each tool
        results: List[DiscoveredTool] = []
        for tool_def in all_tools:
            score, reason = self._calculate_relevance(query, tool_def, context)

            if score >= self._min_relevance_threshold:
                # Check if the required feature is enabled
                is_enabled = True
                required_feature = None

                if tool_def.feature_flag:
                    is_enabled = tool_def.feature_flag in context.enabled_features
                    if not is_enabled:
                        required_feature = FEATURE_FLAG_DISPLAY_NAMES.get(
                            tool_def.feature_flag,
                            tool_def.feature_flag.replace("_", " ").title()
                        )

                # Check MCP tool connection status (includes user-specific tools)
                catalog_entry = self.catalog.get_entry(tool_def.id, user_id=context.user_id)

                # Determine connection status
                # MCP tools without a catalog entry should default to NOT connected
                # Core tools (non-MCP) are always available
                is_mcp_tool = (
                    tool_def.feature_flag == "mcp_tools" or
                    tool_def.id.startswith("mcp_")
                )
                is_connected = not is_mcp_tool  # Core tools are always connected, MCP tools need verification
                mcp_server_name = None
                mcp_server_icon = None
                mcp_server_icon_invert = False

                if catalog_entry:
                    # Check if tool is available (connected)
                    is_connected = catalog_entry.is_available

                    # Get server info from catalog entry
                    mcp_server_name = catalog_entry.mcp_server_name
                    mcp_server_icon = catalog_entry.mcp_server_icon
                    mcp_server_icon_invert = catalog_entry.mcp_server_icon_invert

                    # Fallback: Extract server name from tags if not in entry
                    if not mcp_server_name:
                        for tag in tool_def.tags:
                            if tag.startswith("server:"):
                                mcp_server_name = tag.replace("server:", "")
                                break
                elif is_mcp_tool:
                    # MCP tool without catalog entry - try to get server name from tags
                    for tag in tool_def.tags:
                        if tag.startswith("server:"):
                            mcp_server_name = tag.replace("server:", "")
                            break

                results.append(DiscoveredTool(
                    definition=tool_def,
                    relevance_score=score,
                    match_reason=reason,
                    catalog_entry=catalog_entry,
                    is_enabled=is_enabled,
                    required_feature=required_feature,
                    is_connected=is_connected,
                    mcp_server_name=mcp_server_name,
                    mcp_server_icon=mcp_server_icon,
                    mcp_server_icon_invert=mcp_server_icon_invert,
                ))

        # Sort by score (descending), but prioritize:
        # 1. Enabled AND connected tools
        # 2. Enabled but not connected
        # 3. Disabled tools
        results.sort(
            key=lambda x: (x.is_enabled, x.is_connected, x.relevance_score),
            reverse=True
        )

        # Limit results
        top_results = results[:max_results]

        # Update context with discovered tools (only enabled AND connected ones for execution)
        for result in top_results:
            if result.is_enabled and result.is_connected:
                context.add_discovered_tool(result.definition.id)

        # Log with enabled/disabled/connected status
        enabled_connected = sum(1 for r in top_results if r.is_enabled and r.is_connected)
        enabled_not_connected = sum(1 for r in top_results if r.is_enabled and not r.is_connected)
        disabled_count = sum(1 for r in top_results if not r.is_enabled)
        logger.info(
            f"[ToolDiscovery] Search '{query}' returned {len(top_results)} tools "
            f"({enabled_connected} ready, {enabled_not_connected} need connection, {disabled_count} disabled) "
            f"[{', '.join(r.definition.id for r in top_results)}]"
        )

        return top_results

    def _calculate_relevance(
        self,
        query: str,
        tool: ToolDefinition,
        context: ToolDiscoveryContext
    ) -> tuple[float, str]:
        """
        Calculate relevance score for a tool.

        Scoring weights:
        - Name match: 0.35
        - Description match: 0.25
        - Keyword match: 0.20
        - Tag match: 0.10
        - Usage boost: 0.05
        - Search boost: 0.05

        Args:
            query: Search query
            tool: Tool definition
            context: Discovery context

        Returns:
            Tuple of (score, reason)
        """
        query_lower = query.lower()
        query_words = set(self._tokenize(query_lower))
        score = 0.0
        reasons = []

        # 1. Name match (weight: 0.35)
        name_lower = tool.name.lower()
        if query_lower in name_lower:
            score += 0.35
            reasons.append("exact name match")
        elif any(word in name_lower for word in query_words):
            word_matches = sum(1 for w in query_words if w in name_lower)
            score += 0.25 * (word_matches / len(query_words))
            reasons.append("partial name match")

        # 2. Description match (weight: 0.25)
        desc_lower = tool.description.lower()
        if query_lower in desc_lower:
            score += 0.25
            reasons.append("exact description match")
        else:
            desc_words = set(self._tokenize(desc_lower))
            desc_matches = query_words & desc_words
            if desc_matches:
                score += 0.15 * (len(desc_matches) / len(query_words))
                reasons.append(f"description: {desc_matches}")

        # 3. Keyword match (weight: 0.20)
        keywords_lower = [k.lower() for k in tool.search_keywords]
        keyword_matches = []
        for keyword in keywords_lower:
            if keyword in query_lower or any(w in keyword for w in query_words):
                keyword_matches.append(keyword)
        if keyword_matches:
            score += 0.20 * min(len(keyword_matches) / 3, 1.0)
            reasons.append(f"keywords: {keyword_matches[:3]}")

        # 4. Tag match (weight: 0.10)
        tags_lower = [t.lower() for t in tool.tags]
        tag_matches = query_words & set(tags_lower)
        if tag_matches:
            score += 0.10 * (len(tag_matches) / len(query_words))
            reasons.append(f"tags: {tag_matches}")

        # 5. Usage boost (weight: 0.05)
        entry = self.catalog.get_entry(tool.id, user_id=context.user_id)
        if entry:
            usage_boost = entry.calculate_relevance_boost() - 1.0  # Normalize
            score += 0.05 * min(usage_boost, 1.0)

        # 6. Search boost from definition (weight: 0.05)
        if tool.search_boost > 1.0:
            score += 0.05 * min(tool.search_boost - 1.0, 0.5)

        # Normalize score
        score = min(score, 1.0)

        reason = " | ".join(reasons) if reasons else "weak match"
        return score, reason

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for matching.

        Removes common stop words and short words.
        """
        # Simple tokenization - split on non-alphanumeric
        words = re.split(r'[^a-z0-9]+', text.lower())

        # Filter short words and stop words
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
            'from', 'as', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'under', 'again', 'further',
            'then', 'once', 'here', 'there', 'when', 'where', 'why',
            'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
            'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or',
            'because', 'until', 'while', 'about', 'against', 'this',
            'that', 'these', 'those', 'what', 'which', 'who', 'whom',
            'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him',
            'his', 'she', 'her', 'it', 'its', 'they', 'them', 'their',
        }

        return [w for w in words if len(w) > 2 and w not in stop_words]

    def get_always_loaded_tools(
        self,
        context: ToolDiscoveryContext
    ) -> List[ToolDefinition]:
        """
        Get tools that should always be loaded for a context.

        Args:
            context: Discovery context

        Returns:
            List of always-loaded tool definitions
        """
        return self.catalog.get_always_loaded_tools(context.enabled_features)

    def get_session_tools(
        self,
        context: ToolDiscoveryContext
    ) -> List[ToolDefinition]:
        """
        Get all tools available in the session.

        Includes:
        - Always-loaded tools
        - Tools discovered via search

        Args:
            context: Discovery context

        Returns:
            List of tool definitions
        """
        tools = []
        seen_ids = set()

        # Always-loaded tools
        for tool in self.get_always_loaded_tools(context):
            if tool.id not in seen_ids:
                tools.append(tool)
                seen_ids.add(tool.id)

        # Discovered tools
        for tool_id in context.discovered_tool_ids:
            if tool_id not in seen_ids:
                discovered_tool = self.catalog.get_tool(tool_id, user_id=context.user_id)
                if discovered_tool:
                    tools.append(discovered_tool)
                    seen_ids.add(tool_id)

        return tools

    def get_tools_for_binding(
        self,
        context: ToolDiscoveryContext,
        include_discovered: bool = True
    ) -> List[ToolDefinition]:
        """
        Get tools ready for LLM binding.

        Returns tools sorted by priority.

        Args:
            context: Discovery context
            include_discovered: Include previously discovered tools

        Returns:
            List of tool definitions for binding
        """
        if include_discovered:
            tools = self.get_session_tools(context)
        else:
            tools = self.get_always_loaded_tools(context)

        # Sort by priority
        tools.sort(key=lambda t: t.priority)

        return tools

    def get_discovery_summary(
        self,
        context: ToolDiscoveryContext
    ) -> Dict[str, Any]:
        """
        Get a summary of discovery activity for a session.

        Args:
            context: Discovery context

        Returns:
            Summary dictionary
        """
        always_loaded = self.get_always_loaded_tools(context)
        discovered_or_none = [
            self.catalog.get_tool(tid, user_id=context.user_id)
            for tid in context.discovered_tool_ids
            if tid not in {t.id for t in always_loaded}
        ]
        discovered: List[ToolDefinition] = [t for t in discovered_or_none if t is not None]

        return {
            "user_id": context.user_id,
            "conversation_id": context.conversation_id,
            "enabled_features": list(context.enabled_features),
            "always_loaded_count": len(always_loaded),
            "discovered_count": len(discovered),
            "total_tools": len(always_loaded) + len(discovered),
            "total_searches": context.total_searches,
            "discovered_tools": [t.id for t in discovered],
        }


# Global service instance
_discovery_service: Optional[ToolDiscoveryService] = None
_service_lock = threading.Lock()


def get_discovery_service() -> ToolDiscoveryService:
    """Get the global tool discovery service instance."""
    global _discovery_service

    if _discovery_service is None:
        with _service_lock:
            if _discovery_service is None:
                _discovery_service = ToolDiscoveryService()

    return _discovery_service
