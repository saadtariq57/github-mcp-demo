"""MCP tool discovery and LangChain conversion."""

from langchain_core.tools import BaseTool
from mcp import Client
from mcp.types import Tool

from src.github_mcp.schema import json_schema_to_pydantic_model
from src.github_mcp.tool import MCPTool


async def list_all_mcp_tools(client: Client) -> list[Tool]:
    """Page through tools/list and return every tool the server exposes."""
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if page.next_cursor is None:
            return tools
        cursor = page.next_cursor


def is_read_only(mcp_tool: Tool) -> bool:
    """True when the server annotates the tool as read-only (readOnlyHint)."""
    return bool(mcp_tool.annotations and mcp_tool.annotations.read_only_hint)


def make_langchain_tools(
    mcp_tools: list[Tool], client: Client, write_repo: str | None = None
) -> list[BaseTool]:
    """Wrap each MCP Tool in an MCPTool LangChain adapter."""
    lc_tools: list[BaseTool] = []
    for mcp_tool in mcp_tools:
        schema = json_schema_to_pydantic_model(
            mcp_tool.name, mcp_tool.input_schema or {}
        )
        lc_tools.append(
            MCPTool(
                name=mcp_tool.name,
                description=mcp_tool.description or mcp_tool.name,
                args_schema=schema,
                client=client,
                read_only=is_read_only(mcp_tool),
                write_repo=write_repo,
            )
        )
    return lc_tools
