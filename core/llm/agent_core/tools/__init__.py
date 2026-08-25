"""One module per tool. `llm.agent_core.registry.discover_tools` walks this
package and imports every module whose name does not start with `_`,
reading its module-level `TOOL: ToolDefinition`.
"""
