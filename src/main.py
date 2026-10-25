"""Application entry point for the GitHub MCP Agent.

Coordinates:
- MCP connection and tool discovery (src.github_mcp)
- Dynamic tool routing (src.router)
- LangGraph agent execution & structured output (src.agent)
- Observability and token logging (src.telemetry)

Usage:
  .venv/bin/python src/main.py "Who am I on GitHub?"
  .venv/bin/python src/main.py "Analyze saadtariq57/github-mcp-demo" --structured
  .venv/bin/python -m src "Find my GitHub repositories that use TypeScript"
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx2
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langchain_core.messages import HumanMessage, SystemMessage
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from src.agent import AGENT_SYSTEM, RepositoryAnalysis, build_graph
from src.github_mcp import list_all_mcp_tools, make_langchain_tools
from src.router import route_tools
from src.telemetry import TokenLogger

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


def _format_startup_error(exc: BaseException) -> str:
    """Extract a user-friendly error message from connection/auth exceptions."""
    err_str = str(exc)
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            sub_msg = _format_startup_error(sub)
            if sub_msg != str(sub):
                return sub_msg
            err_str = str(sub)

    if "ConnectError" in type(exc).__name__ or "ConnectError" in err_str or "No address associated with hostname" in err_str:
        return "Connection failed: Unable to reach the GitHub MCP server. Please check your network connection and GITHUB_MCP_URL."
    if "MCPError" in type(exc).__name__ or "Server returned an error response" in err_str:
        return "Authentication / MCP error: The GitHub MCP server rejected the connection. Please verify that your GITHUB_PERSONAL_ACCESS_TOKEN in .env is valid and has required scopes."
    return f"{type(exc).__name__}: {exc}"


async def run(question: str, structured: bool = False) -> None:
    """Run a user query through the MCP agent."""
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    if not token:
        print("Missing GITHUB_PERSONAL_ACCESS_TOKEN in .env")
        sys.exit(1)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("Missing OPENROUTER_API_KEY in .env")
        sys.exit(1)

    model_name   = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    router_model = os.getenv("OPENROUTER_ROUTER_MODEL", "openai/gpt-4o-mini").strip()
    url = os.getenv("GITHUB_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL

    try:
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx2.Timeout(30.0, read=300.0),
        ) as http_client:
            transport = streamable_http_client(url, http_client=http_client)
            async with Client(transport) as mcp_client:
                print(f"Connected to GitHub MCP Server ({url})")

                # 1. Discover all MCP tools & wrap into LangChain tools.
                mcp_tools = await list_all_mcp_tools(mcp_client)
                print(f"Discovered {len(mcp_tools)} MCP tools")
                lc_tools = make_langchain_tools(mcp_tools, mcp_client)

                # 2. Route tools: select only what the user question needs.
                logger = TokenLogger(question=question, model=model_name)
                print("Routing tools...")
                selected_names = await route_tools(
                    question=question,
                    mcp_tools=mcp_tools,
                    api_key=api_key,
                    router_model=router_model,
                    logger=logger,
                )
                filtered_tools = [t for t in lc_tools if t.name in set(selected_names)]
                print(f"Router selected {len(filtered_tools)}/{len(lc_tools)} tools: {selected_names}")

                # 3. Build & execute the LangGraph graph (optionally with structured response format).
                response_format = RepositoryAnalysis if structured else None
                app = build_graph(
                    filtered_tools,
                    model_name,
                    api_key,
                    logger=logger,
                    response_format=response_format,
                )

                print(f"Using model: {model_name}")
                print(f"Question: {question}")
                if structured:
                    print("Structured Mode: enabled (RepositoryAnalysis)")
                print("---")

                result = await app.ainvoke(
                    {"messages": [SystemMessage(content=AGENT_SYSTEM), HumanMessage(content=question)]}
                )

                # 4. Print conversation transcript.
                for message in result["messages"]:
                    if isinstance(message, SystemMessage):
                        continue
                    kind = type(message).__name__
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls:
                        for tc in tool_calls:
                            print(f"{kind}: tool_call → {tc['name']}({json.dumps(tc['args'])})")
                    elif getattr(message, "name", None):
                        print(f"ToolMessage ({message.name}):\n{message.content}")
                    else:
                        print(f"{kind}: {message.content}")

                # 5. Print structured output if present.
                structured_res = result.get("structured_response")
                if structured_res:
                    print("\n" + "=" * 60)
                    print("Structured Output (RepositoryAnalysis):")
                    print("=" * 60)
                    if hasattr(structured_res, "model_dump_json"):
                        print(structured_res.model_dump_json(indent=2))
                    else:
                        print(json.dumps(structured_res, indent=2))
                    print("=" * 60)

                print("---")
                logger.finalize()
                if structured:
                    print("Stage 10 OK")
    except Exception as exc:
        print(f"\n[Fatal Error] {_format_startup_error(exc)}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitHub MCP Agent runner.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Who am I on GitHub?",
        help="Question or task for the agent",
    )
    parser.add_argument(
        "-s", "--structured",
        action="store_true",
        help="Return machine-consumable RepositoryAnalysis structured output",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args.question, structured=args.structured))


if __name__ == "__main__":
    main()
