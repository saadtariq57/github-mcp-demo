"""Stage 7: connect GitHub MCP tools to a LangGraph agent.

The MCP client (Stages 3-5) and the LangGraph agent (Stage 6) are combined
here for the first time.  No adapter library is used.  The bridge is explicit:

  1. Open an MCP session and page through tools/list.
  2. For each MCP tool, create a LangChain BaseTool whose _arun method
     calls the MCP server via client.call_tool.
  3. Bind those tools to the model and wire them into a LangGraph graph.

The graph then runs a single user question that requires a GitHub tool call.

Usage:
  .venv/bin/python scripts/mcp_agent.py
  .venv/bin/python scripts/mcp_agent.py "Who am I on GitHub?"
  .venv/bin/python scripts/mcp_agent.py "List branches in saadtariq57/github-mcp-demo"
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Optional, TypedDict

import httpx2
from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import EmbeddedResource, ResourceLink, TextContent, Tool
from pydantic import BaseModel, Field, create_model

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_MCP_URL = "https://api.githubcopilot.com/mcp/"


# ---------------------------------------------------------------------------
# JSON Schema → Pydantic bridge
# ---------------------------------------------------------------------------

def _json_schema_to_python_type(field_schema: dict) -> Any:
    """Best-effort conversion of a JSON Schema field descriptor to a Python type.

    Handles the common subset used by the GitHub MCP server:
    string / integer / number / boolean / array / object and anyOf/oneOf
    (pick first non-null variant).
    """
    for combiner in ("anyOf", "oneOf"):
        if combiner in field_schema:
            for variant in field_schema[combiner]:
                if variant.get("type") != "null":
                    return Optional[_json_schema_to_python_type(variant)]
            return Optional[Any]

    t = field_schema.get("type", "string")
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        return list
    if t == "object":
        return dict
    return Any


def json_schema_to_pydantic_model(tool_name: str, json_schema: dict) -> type[BaseModel]:
    """Build a Pydantic model with *declared* fields from an MCP tool's input schema.

    LangChain reads declared fields (not model_extra) when unpacking kwargs for
    _run / _arun, so every parameter the MCP server expects must be a real field.
    """
    props: dict = json_schema.get("properties") or {}
    required: set[str] = set(json_schema.get("required") or [])
    field_defs: dict[str, Any] = {}

    for field_name, field_schema in props.items():
        python_type = _json_schema_to_python_type(field_schema)
        description = field_schema.get("description", "")
        if field_name in required:
            field_defs[field_name] = (python_type, Field(description=description))
        else:
            field_defs[field_name] = (
                Optional[python_type],
                Field(default=None, description=description),
            )

    # create_model with no fields → tool takes no arguments (e.g. get_me)
    return create_model(f"{tool_name}Input", **field_defs)


# ---------------------------------------------------------------------------
# MCP → LangChain bridge
# ---------------------------------------------------------------------------


class MCPTool(BaseTool):
    """A LangChain tool whose implementation lives in the MCP server.

    `args_schema` is a Pydantic model built from the tool's MCP JSON Schema
    so that LangChain correctly unpacks the model's declared fields as **kwargs
    into _arun.  `client` is the live MCP session.
    """

    name: str
    description: str
    args_schema: type[BaseModel]  # set per-tool in make_langchain_tools
    client: Any  # mcp.Client — Any to keep Pydantic happy

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> str:  # type: ignore[override]
        raise NotImplementedError("Use async path only.")

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        result = await self.client.call_tool(self.name, kwargs)

        if result.is_error:
            # Return the error as a string so LangGraph's ToolNode wraps it in a
            # ToolMessage and feeds it back to the model.  Raising here would crash
            # the anyio TaskGroup and prevent the model from recovering gracefully.
            pieces = _extract_text(result.content)
            return f"[MCP error from {self.name!r}]: {pieces}"

        return _extract_text(result.content)


def _extract_text(content: list) -> str:
    """Pull readable text out of an MCP content block list."""
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


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

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


def make_langchain_tools(mcp_tools: list[Tool], client: Client) -> list[BaseTool]:
    """Wrap each MCP Tool in an MCPTool LangChain adapter.

    Each tool gets a Pydantic schema built from its MCP JSON Schema so that
    LangChain can correctly unpack the declared fields as **kwargs into _arun.
    """
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
            )
        )
    return lc_tools


# ---------------------------------------------------------------------------
# LangGraph graph
# ---------------------------------------------------------------------------

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def build_graph(tools: list[BaseTool], model_name: str, api_key: str) -> Any:
    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/saadtariq57/github-mcp-demo",
            "X-Title": "github-mcp-demo",
        },
    ).bind_tools(tools)

    def chatbot(state: State) -> dict:
        return {"messages": [model.invoke(state["messages"])]}

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", tools_condition)
    graph.add_edge("tools", "chatbot")
    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(question: str) -> None:
    token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    if not token:
        print("Missing GITHUB_PERSONAL_ACCESS_TOKEN in .env")
        sys.exit(1)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("Missing OPENROUTER_API_KEY in .env")
        sys.exit(1)

    model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
    url = os.getenv("GITHUB_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL

    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as mcp_client:
            print(f"Connected to GitHub MCP Server ({url})")

            # 1. Discover tools and wrap them.
            mcp_tools = await list_all_mcp_tools(mcp_client)
            print(f"Discovered {len(mcp_tools)} MCP tools")

            lc_tools = make_langchain_tools(mcp_tools, mcp_client)

            # 2. Build and run the graph.
            app = build_graph(lc_tools, model_name, api_key)

            print(f"Using model: {model_name}")
            print(f"Question: {question}")
            print("---")

            result = await app.ainvoke(
                {"messages": [HumanMessage(content=question)]}
            )

            # 3. Print the conversation transcript.
            for message in result["messages"]:
                kind = type(message).__name__
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        print(f"{kind}: tool_call → {tc['name']}({json.dumps(tc['args'])})")
                elif getattr(message, "name", None):
                    # ToolMessage — the MCP result returned to the model
                    print(f"ToolMessage ({message.name}):\n{message.content}")
                else:
                    print(f"{kind}: {message.content}")

            print("---")
            print("Stage 7 OK")


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Who am I on GitHub?"
    asyncio.run(run(question))
