"""The per-request feature switches a chat turn was created with.

One value object, two views onto it. The tool-discovery context and the
V2 prompt builder each want a *set of feature names*, and those two sets
are deliberately NOT the same: the prompt builder is told about sparks,
the discovery context is not. Keeping both derivations here makes that
asymmetry explicit instead of leaving it to diverge across two
near-identical inline blocks.
"""

from dataclasses import dataclass

# Feature names as the prompt builder and discovery service know them.
FEATURE_FILE_TOOLS = "file_tools"
FEATURE_BRAVE_SEARCH = "brave_search"
FEATURE_GOOGLE_MAPS = "google_maps"
FEATURE_REASONING = "reasoning"
FEATURE_MCP_TOOLS = "mcp_tools"
FEATURE_VOICE_MODE = "voice_mode"
FEATURE_IMAGE_GENERATION = "image_generation"
FEATURE_VIDEO_GENERATION = "video_generation"
FEATURE_SPARKS = "sparks"
FEATURE_KNOWLEDGE_BASE = "knowledge_base"


@dataclass(frozen=True)
class AgentFeatureFlags:
    """Immutable snapshot of the per-request tool/capability switches."""

    file_tools: bool = False
    brave_search: bool = False
    google_maps: bool = False
    image_generation: bool = False
    video_generation: bool = False
    reasoning: bool = False
    mcp_tools: bool = False
    voice_mode: bool = False
    sparks: bool = False
    knowledge_base: bool = False

    @property
    def has_tool_features(self) -> bool:
        """Whether any *tool*-backed feature is on.

        Web search and reasoning are model capabilities rather than
        tools, so they do not count towards enabling tool discovery.
        """
        return (
            self.file_tools
            or self.brave_search
            or self.google_maps
            or self.image_generation
            or self.video_generation
            or self.mcp_tools
        )

    def _common_feature_names(self) -> set:
        names = set()
        if self.file_tools:
            names.add(FEATURE_FILE_TOOLS)
        if self.brave_search:
            names.add(FEATURE_BRAVE_SEARCH)
        if self.google_maps:
            names.add(FEATURE_GOOGLE_MAPS)
        if self.reasoning:
            names.add(FEATURE_REASONING)
        if self.mcp_tools:
            names.add(FEATURE_MCP_TOOLS)
        if self.voice_mode:
            names.add(FEATURE_VOICE_MODE)
        if self.image_generation:
            names.add(FEATURE_IMAGE_GENERATION)
        if self.video_generation:
            names.add(FEATURE_VIDEO_GENERATION)
        if self.knowledge_base:
            names.add(FEATURE_KNOWLEDGE_BASE)
        return names

    def discovery_feature_names(self) -> set:
        """Feature set handed to `ToolDiscoveryService.get_or_create_context`.

        Sparks are intentionally absent: discovery never gated on them.
        """
        return self._common_feature_names()

    def prompt_feature_names(self) -> set:
        """Feature set handed to the V2 prompt builder (sparks included)."""
        names = self._common_feature_names()
        if self.sparks:
            names.add(FEATURE_SPARKS)
        return names
