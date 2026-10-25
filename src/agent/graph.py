"""LangGraph state machine graph construction."""

import json
from typing import Any, Optional, Type

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel

from src.agent.state import State
from src.telemetry import TokenLogger


def build_graph(
    tools: list[BaseTool],
    model_name: str,
    api_key: str,
    logger: TokenLogger | None = None,
    response_format: Optional[Type[BaseModel]] = None,
) -> Any:
    """Build and compile the LangGraph agent state machine.

    If `response_format` is provided, once the agent completes its tool-calling
    loop, the graph transitions to an extractor node that converts the verified
    findings into a typed, validated Pydantic model.
    """
    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/saadtariq57/github-mcp-demo",
            "X-Title": "github-mcp-demo",
        },
    ).bind_tools(tools)

    def _summarize_tool_call(tc: dict) -> str:
        """Return a compact one-liner for a single tool call."""
        args = tc.get("args") or {}
        # Prefer 'path' when present; otherwise show up to 2 key=value pairs.
        if args.get("path") is not None:
            arg_str = f'path="{args["path"]}"'
        else:
            arg_str = ", ".join(
                f"{k}={v}" for k, v in args.items()
                if v is not None and k not in ("sha", "ref", "fields")
            )[:40]
        name = tc["name"]
        return f"{name}({arg_str})"

    def chatbot(state: State) -> dict:
        response = model.invoke(state["messages"])
        usage = getattr(response, "usage_metadata", None)
        if usage and logger is not None:
            tool_calls = getattr(response, "tool_calls", None)
            if tool_calls:
                action = "; ".join(_summarize_tool_call(tc) for tc in tool_calls)
            else:
                action = "[response]"
            logger.record(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                action=action,
            )
        return {"messages": [response]}

    def route_after_chatbot(state: State) -> str:
        condition = tools_condition(state)
        if condition == "tools":
            return "tools"
        if response_format is not None:
            return "extractor"
        return END

    def extractor(state: State) -> dict:
        extractor_llm = ChatOpenAI(
            model=model_name,   
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/saadtariq57/github-mcp-demo",
                "X-Title": "github-mcp-demo",
            },
        ).with_structured_output(
            response_format,
            method="function_calling",
            include_raw=True,
        )

        prompt = [
            SystemMessage(
                content=(
                    "Extract the structured schema from the conversation history and verified tool findings. "
                    "If the repository could not be found, does not exist, or analysis failed, set 'error' to a "
                    "concise explanation (e.g. 'Repository not found (404)') and leave unknown fields null or empty."
                )
            )
        ] + [m for m in state["messages"] if not isinstance(m, SystemMessage)]

        res = extractor_llm.invoke(prompt)
        parsed = res.get("parsed") if isinstance(res, dict) else res
        raw = res.get("raw") if isinstance(res, dict) else None
        if raw and logger is not None:
            usage = getattr(raw, "usage_metadata", None)
            if usage:
                schema_name = response_format.__name__ if response_format else "structured"
                logger.record(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    action=f"[extractor → {schema_name}]",
                )
        return {"structured_response": parsed}

    def _summarize_tool_result(tool_name: str, content: str) -> str:
        """Return a one-line summary of a tool result for the trace log."""
        content = content.strip()
        # Directory listing – JSON array of file/dir objects
        if content.startswith("["):
            try:
                items = json.loads(content)
                if isinstance(items, list):
                    names = [item.get("name", "?") for item in items[:5]]
                    suffix = ", ..." if len(items) > 5 else ""
                    return f"dir: {len(items)} entries ({', '.join(names)}{suffix})"
            except Exception:
                pass
        # File download – MCP prepends a status line
        if "successfully downloaded" in content:
            body = content.split("\n", 1)[1] if "\n" in content else ""
            return f"text: {len(body):,} chars"
        # Fallback – first 80 chars on one line
        return content[:80].replace("\n", " ")

    _tool_node = ToolNode(tools, handle_tool_errors=True)

    async def tools_with_logging(state: State) -> dict:
        """Run tools and log a concise summary of each result."""
        result = await _tool_node.ainvoke(state)
        if logger is not None:
            for msg in result.get("messages", []):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary = _summarize_tool_result(getattr(msg, "name", ""), content)
                logger.record_tool_result(getattr(msg, "name", "tool"), summary)
        return result

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", tools_with_logging)

    graph.add_edge(START, "chatbot")
    graph.add_edge("tools", "chatbot")

    if response_format is not None:
        graph.add_node("extractor", extractor)
        graph.add_conditional_edges(
            "chatbot",
            route_after_chatbot,
            {"tools": "tools", "extractor": "extractor"},
        )
        graph.add_edge("extractor", END)
    else:
        graph.add_conditional_edges("chatbot", tools_condition)

    return graph.compile()
