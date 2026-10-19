"""Tools package for SENSAI."""

from src.features.tools.executor import ToolExecutionResult, ToolExecutor
from src.features.tools.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPProtocolError,
    MCPTimeoutError,
    MCPTool,
)
from src.features.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    default_registry,
    extract_tool_schema,
    tool,
)
from src.features.tools import web_search

__all__ = [
    "MCPClient",
    "MCPConnectionError",
    "MCPError",
    "MCPProtocolError",
    "MCPTimeoutError",
    "MCPTool",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolExecutor",
    "ToolRegistry",
    "default_registry",
    "extract_tool_schema",
    "tool",
    "web_search",
]
