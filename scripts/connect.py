"""Stage 3: connect a Python MCP client to GitHub's hosted MCP server."""

import asyncio
import os
import sys
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


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
            print("Connected to GitHub MCP Server")
            print(f"URL: {url}")
            info = client.server_info
            if info is not None:
                print(f"Server: {info.name} {info.version}")
            print(f"Protocol: {client.protocol_version}")
            tools = client.server_capabilities.tools if client.server_capabilities else None
            print(f"Tools capability: {'yes' if tools else 'no'}")
            print("Stage 3 OK")

if __name__ == "__main__":
    asyncio.run(main())
