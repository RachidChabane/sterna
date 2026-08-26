"""The bound callables one V2 chat request's feature switches entitle it to.

Registry. Owns three pieces of state `llm.agent_service.registry_factory`
reads once a turn is built:

* ``tools``           -- the LangChain tool objects bound for this request.
* ``display_names``   -- tool id -> human label shown in the UI.
* ``server_icons``    -- tool id -> MCP server icon descriptor.

Every switch adds its own tool group and, where the group needs one, its
own display-name mapping. The coding-agent and plan tools ride along
with file tools, since they only make sense inside a workspace.
"""

from typing import Any, Dict, List

from ..agent_tool_handlers import CODING_AGENT_TOOL, FILE_TOOLS, PLAN_TOOLS
from ..asset_tools import ASSET_TOOLS
from ..brave_search_tools import BRAVE_SEARCH_TOOLS
from ..google_maps_tools import GOOGLE_MAPS_TOOLS
from ..image_tools import IMAGE_TOOLS
from ..knowledge_base_tools import KNOWLEDGE_BASE_TOOLS
from ..spark_tools import SPARK_TOOLS
from ..video_tools import VIDEO_TOOLS
from ..web_fetch_tools import WEB_FETCH_TOOLS
from .feature_flags import AgentFeatureFlags

SPARK_TOOL_DISPLAY_NAMES = {
    "create_spark": "Create Spark",
    "update_spark": "Update Spark",
}

KNOWLEDGE_BASE_TOOL_DISPLAY_NAMES = {
    "list_knowledge_base_documents": "List Knowledge Base",
    "query_knowledge_base": "Query Knowledge Base",
}

ASSET_TOOL_DISPLAY_NAMES = {
    "get_image": "Get Image",
    "get_video": "Get Video",
    "get_spark": "Get Spark",
    "get_document": "Get Document",
    "export_asset": "Export Asset",
    "save_asset_to_workspace": "Save to Workspace",
}


class AgentToolRegistry:
    """The tool set one request's feature flags bind."""

    def __init__(self, flags: AgentFeatureFlags):
        self._flags = flags
        self.tools: List[Any] = []
        self.display_names: Dict[str, str] = {}

    def load_initial_tools(self) -> None:
        """Populate `tools`/`display_names` for every switch this request has on."""

        flags = self._flags
        if flags.file_tools:
            self.tools.extend(FILE_TOOLS)
            self.tools.append(CODING_AGENT_TOOL)
            self.tools.extend(PLAN_TOOLS)
        if flags.brave_search:
            self.tools.extend(BRAVE_SEARCH_TOOLS)
            self.tools.extend(WEB_FETCH_TOOLS)
        if flags.google_maps:
            self.tools.extend(GOOGLE_MAPS_TOOLS)
        if flags.image_generation:
            self.tools.extend(IMAGE_TOOLS)
        if flags.video_generation:
            self.tools.extend(VIDEO_TOOLS)
        if flags.sparks:
            self.tools.extend(SPARK_TOOLS)
            self.display_names.update(SPARK_TOOL_DISPLAY_NAMES)
        if flags.knowledge_base:
            self.tools.extend(KNOWLEDGE_BASE_TOOLS)
            self.display_names.update(KNOWLEDGE_BASE_TOOL_DISPLAY_NAMES)

        # Asset access tools for reading images, videos, sparks, documents
        # are offered on every request, regardless of which other
        # switches are on.
        self.tools.extend(ASSET_TOOLS)
        self.display_names.update(ASSET_TOOL_DISPLAY_NAMES)
