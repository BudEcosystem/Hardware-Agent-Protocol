"""Agent bridges: the eight BHMS tools (:mod:`bhms.bridges.core`) for MCP clients (:mod:`bhms.bridges.mcp`) and for OpenAI
function calling (:mod:`bhms.bridges.openai_tools`)."""

from bhms.bridges.core import AgentBridge, ToolDef, ToolResult, tool_definitions

__all__ = ["AgentBridge", "ToolDef", "ToolResult", "tool_definitions"]
