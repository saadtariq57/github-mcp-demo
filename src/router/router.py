"""LLM-based tool selector."""

import json
import re
from typing import Any

from langchain_openai import ChatOpenAI
from mcp.types import Tool

from src.router.catalog import build_catalog
from src.router.prompts import ROUTER_SYSTEM


async def route_tools(
    question: str,
    mcp_tools: list[Tool],
    api_key: str,
    router_model: str,
    logger: Any | None = None,
) -> list[str]:
    """Ask a lightweight model which tools are needed and return their names.

    Falls back to all tool names if parsing fails so the agent can still run.
    """
    catalog = build_catalog(mcp_tools)
    user_msg = f"User question: {question}\n\nAvailable tools:\n{catalog}"

    router_llm = ChatOpenAI(
        model=router_model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/saadtariq57/github-mcp-demo",
            "X-Title": "github-mcp-demo",
        },
    )

    response = await router_llm.ainvoke([
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "user",   "content": user_msg},
    ])

    usage = getattr(response, "usage_metadata", None)
    if usage and logger is not None and hasattr(logger, "record_router"):
        logger.record_router(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    raw = response.content.strip()
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        return [t.name for t in mcp_tools]

    try:
        selected: list[str] = json.loads(match.group())
        if not isinstance(selected, list):
            raise ValueError("not a list")
        return [s for s in selected if isinstance(s, str)]
    except (json.JSONDecodeError, ValueError):
        return [t.name for t in mcp_tools]
