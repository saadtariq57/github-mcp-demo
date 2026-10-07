"""LangChain BaseTool adapter for live MCP tools."""

import json
from typing import Any

from langchain_core.tools import BaseTool
from mcp.types import EmbeddedResource, ResourceLink, TextContent
from pydantic import BaseModel


def extract_mcp_text(content: list) -> str:
    """Extract readable string content from MCP content blocks."""
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextContent):
            try:
                parsed = json.loads(block.text)
                parts.append(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                parts.append(block.text)
        elif isinstance(block, ResourceLink):
            parts.append(str(block.uri))
        elif isinstance(block, EmbeddedResource):
            text = getattr(block.resource, "text", None)
            if text is not None:
                try:
                    parts.append(json.dumps(json.loads(text), indent=2))
                except json.JSONDecodeError:
                    parts.append(text)
            else:
                parts.append(repr(block.resource))
        else:
            parts.append(repr(block))
    return "\n".join(parts)


class MCPTool(BaseTool):
    """A LangChain tool whose implementation delegates to the MCP server."""

    name: str
    description: str
    args_schema: type[BaseModel]
    client: Any  # mcp.Client

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> str:  # type: ignore[override]
        raise NotImplementedError("Use async path only.")

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        # Strip None values — optional params must be omitted, not sent as null.
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        result = await self.client.call_tool(self.name, filtered)

        if result.is_error:
            pieces = extract_mcp_text(result.content)
            return f"[MCP error from {self.name!r}]: {pieces}"

        return extract_mcp_text(result.content)
