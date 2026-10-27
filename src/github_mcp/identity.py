"""Resolve the authenticated GitHub user once, in code, before the agent runs."""

import json

from mcp import Client

from src.github_mcp.tool import extract_mcp_text


async def get_authenticated_login(client: Client) -> str | None:
    """Return the token owner's login via get_me, or None if it can't be read."""
    try:
        result = await client.call_tool("get_me", {})
        if result.is_error:
            return None
        return json.loads(extract_mcp_text(result.content)).get("login")
    except Exception:
        return None
