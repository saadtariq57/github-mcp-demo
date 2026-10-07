"""Stage 4: list tools and schemas from GitHub's hosted MCP server."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


async def list_all_tools(client: Client) -> list[Tool]:
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if page.next_cursor is None:
            return tools
        cursor = page.next_cursor


def print_tool(tool: Tool, index: int) -> None:
    schema = tool.input_schema or {}
    props: dict = schema.get("properties") or {}
    required: set = set(schema.get("required") or [])

    print(f"  {index:>2}. {tool.name}")
    if tool.description:
        # Print first line of description only for brevity
        first_line = tool.description.strip().splitlines()[0]
        print(f"      {first_line}")
    if props:
        print("      Parameters:")
        for param, info in props.items():
            req_marker = "*" if param in required else " "
            ptype = info.get("type", "any")
            desc = info.get("description", "").splitlines()[0][:60]
            print(f"        {req_marker} {param} ({ptype}) — {desc}")
    else:
        print("      Parameters: none")


async def main() -> None:
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    if not token:
        print("Missing GITHUB_PERSONAL_ACCESS_TOKEN in .env")
        sys.exit(1)

    url = os.getenv("GITHUB_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL

    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            tools = await list_all_tools(client)
            print(f"\n{'─' * 55}")
            print(f"  GitHub MCP Tools ({len(tools)} total)")
            print(f"{'─' * 55}")
            print("  * = required parameter\n")
            for i, tool in enumerate(tools, start=1):
                print_tool(tool, i)
            print(f"\n{'─' * 55}")
            print(f"  Total: {len(tools)} tools")
            print(f"{'─' * 55}")
            print("\nStage 4 OK")


if __name__ == "__main__":
    asyncio.run(main())
