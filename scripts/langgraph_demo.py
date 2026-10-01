"""Stage 6: a minimal LangGraph agent. No GitHub MCP.

Uses OpenRouter (OpenAI-compatible) when OPENROUTER_API_KEY is set.
"""

import os
import sys
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_URL = "https://openrouter.ai/api/v1"


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@tool
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    print(f"tool executed: add({a}, {b})")
    return a + b


TOOLS = [add]


def build_model():
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("Missing OPENROUTER_API_KEY in .env")
        sys.exit(1)

    model_name = os.getenv("OPENROUTER_MODEL", "openai/gpt-5-mini").strip()
    print(f"Using OpenRouter model: {model_name}")
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=OPENROUTER_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/saadtariq57/github-mcp-demo",
            "X-Title": "github-mcp-demo",
        },
    ).bind_tools(TOOLS)


def build_graph():
    model = build_model()

    def chatbot(state: State) -> dict:
        return {"messages": [model.invoke(state["messages"])]}

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", tools_condition)
    graph.add_edge("tools", "chatbot")
    return graph.compile()


def main() -> None:
    app = build_graph()
    result = app.invoke({"messages": [HumanMessage(content="What is 3 + 4? Use the add tool.")]})
    print("--- transcript ---")
    for message in result["messages"]:
        kind = type(message).__name__
        if getattr(message, "tool_calls", None):
            print(f"{kind}: tool_calls={message.tool_calls}")
        else:
            print(f"{kind}: {message.content}")
    print("Stage 6 OK")


if __name__ == "__main__":
    main()
