"""Stage 5: call an MCP tool with no LLM.

Examples:
  .venv/bin/python scripts/invoke.py
  .venv/bin/python scripts/invoke.py get_me
  .venv/bin/python scripts/invoke.py list_branches '{"owner":"saadtariq57","repo":"github-mcp-demo"}'
  .venv/bin/python scripts/invoke.py get_file_contents '{"owner":"saadtariq57","repo":"github-mcp-demo","path":"README.md"}'
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import EmbeddedResource, ResourceLink, TextContent

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call one GitHub MCP tool.")
    parser.add_argument("tool", nargs="?", default="get_me", help="Tool name from tools/list")
    parser.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help='JSON object of tool arguments, e.g. \'{"owner":"x","repo":"y"}\'',
    )
    return parser.parse_args()


def parse_arguments(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"arguments must be JSON: {exc}")
        sys.exit(1)
    if not isinstance(value, dict):
        print("arguments must be a JSON object")
        sys.exit(1)
    return value


def format_text(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2)
    except json.JSONDecodeError:
        return text


async def main() -> None:
    args = parse_args()
    tool_name = args.tool
    tool_arguments = parse_arguments(args.arguments)

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
            # GitHub annotates owner/repo with x-mcp-header. list_tools first so
            # the client can send matching Mcp-Param-* HTTP headers on tools/call.
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor

            result = await client.call_tool(tool_name, tool_arguments)
            print(f"Called tool: {tool_name}")
            print(f"arguments: {json.dumps(tool_arguments)}")
            print(f"is_error: {result.is_error}")
            if result.structured_content is not None:
                print("structured_content:")
                print(json.dumps(result.structured_content, indent=2))
            else:
                print("content:")
                for block in result.content:
                    if isinstance(block, TextContent):
                        print(format_text(block.text))
                    elif isinstance(block, ResourceLink):
                        print(f"resource_link: {block.uri}")
                    elif isinstance(block, EmbeddedResource):
                        resource = block.resource
                        text = getattr(resource, "text", None)
                        if text is not None:
                            print(format_text(text))
                        else:
                            print(resource)
                    else:
                        print(block)
            if result.is_error:
                sys.exit(1)
            print("Stage 5 OK")


if __name__ == "__main__":
    asyncio.run(main())
