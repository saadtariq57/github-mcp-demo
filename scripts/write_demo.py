"""Stage 12: direct, controlled GitHub write calls with no LLM.

Runs a fixed sequence on GITHUB_WRITE_REPO only:
  create_branch → create_or_update_file (the commit) → get_file_contents → create_pull_request

Example:
  .venv/bin/python scripts/write_demo.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.github_mcp.tool import extract_mcp_text  # noqa: E402

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


async def call(client: Client, tool: str, arguments: dict) -> str:
    """Call one tool, print the result, and stop the script on is_error."""
    print(f"\n▶ {tool}({json.dumps(arguments)[:120]})")
    result = await client.call_tool(tool, arguments)
    text = extract_mcp_text(result.content)
    print(f"is_error: {result.is_error}")
    print(text[:600])
    if result.is_error:
        print(f"\nStopped: {tool} failed.")
        sys.exit(1)
    return text


async def main() -> None:
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    write_repo = os.getenv("GITHUB_WRITE_REPO", "").strip()
    if not token:
        print("Missing GITHUB_PERSONAL_ACCESS_TOKEN in .env")
        sys.exit(1)
    if "/" not in write_repo:
        print("Missing GITHUB_WRITE_REPO (owner/repo) in .env — refusing to write anywhere.")
        sys.exit(1)
    owner, repo = write_repo.split("/", 1)

    url = os.getenv("GITHUB_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"stage12-demo-{stamp}"
    path = "stage12/hello.md"

    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            # list_tools first so the client sends matching Mcp-Param-* headers (see invoke.py).
            cursor: str | None = None
            while True:
                page = await client.list_tools(cursor=cursor)
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor

            print(f"Write target: {write_repo}  branch: {branch}")
            repo_args = {"owner": owner, "repo": repo}

            await call(client, "create_branch", {**repo_args, "branch": branch, "from_branch": "main"})
            await call(client, "create_or_update_file", {
                **repo_args,
                "branch": branch,
                "path": path,
                "content": f"# Stage 12\n\nWritten directly through the GitHub MCP server at {stamp}.\n",
                "message": "Stage 12: add hello.md via MCP",
            })
            await call(client, "get_file_contents", {**repo_args, "path": path, "ref": f"refs/heads/{branch}"})
            await call(client, "create_pull_request", {
                **repo_args,
                "title": f"Stage 12 demo ({stamp})",
                "head": branch,
                "base": "main",
                "body": "Opened by scripts/write_demo.py through the GitHub MCP server.",
            })
            print("\nStage 12 direct OK")


if __name__ == "__main__":
    asyncio.run(main())
