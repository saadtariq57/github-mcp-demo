"""Application entry point for the GitHub MCP Agent.

Coordinates:
- MCP connection and tool discovery (src.github_mcp)
- Dynamic tool routing (src.router)
- LangGraph agent execution (src.agent)
- Observability and token logging (src.telemetry)

Usage:
  .venv/bin/python src/main.py "Who am I on GitHub?"
  .venv/bin/python src/main.py "Find my GitHub repositories that use TypeScript"
  .venv/bin/python -m src "What is the entry point for saadtariq57/github-mcp-demo?"
"""

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

from src.agent import AGENT_SYSTEM, build_graph
from src.github_mcp import list_all_mcp_tools, make_langchain_tools
from src.router import route_tools
from src.telemetry import TokenLogger

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


async def run(question: str) -> None:
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

            # 3. Build & execute the LangGraph graph.
            app = build_graph(filtered_tools, model_name, api_key, logger)

            print(f"Using model: {model_name}")
            print(f"Question: {question}")
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

            print("---")
            logger.finalize()


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "Who am I on GitHub?"
    asyncio.run(run(question))


if __name__ == "__main__":
    main()
