"""LangGraph state machine graph construction."""

from typing import Any

from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.agent.state import State
from src.telemetry import TokenLogger


def build_graph(
    tools: list[BaseTool],
    model_name: str,
    api_key: str,
    logger: TokenLogger | None = None,
) -> Any:
    """Build and compile the LangGraph agent state machine."""
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
        response = model.invoke(state["messages"])
        usage = getattr(response, "usage_metadata", None)
        if usage and logger is not None:
            logger.record(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        return {"messages": [response]}

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "chatbot")
    graph.add_conditional_edges("chatbot", tools_condition)
    graph.add_edge("tools", "chatbot")
    return graph.compile()
