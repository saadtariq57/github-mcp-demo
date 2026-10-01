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


def print_tool(tool: Tool) -> None:
    print(f"\n=== {tool.name} ===")
    if tool.description:
        print(tool.description.strip())
    schema = tool.input_schema or {}
    print("inputSchema:")
    print(json.dumps(schema, indent=2))


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
            print(f"Discovered {len(tools)} tools via tools/list")
            for tool in tools:
                print_tool(tool)
            print("\nStage 4 OK")


if __name__ == "__main__":
    asyncio.run(main())
