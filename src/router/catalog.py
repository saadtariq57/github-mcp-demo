"""Compact tool catalog builder for the router LLM."""

from mcp.types import Tool


def build_catalog(tools: list[Tool], max_desc_len: int = 150) -> str:
    """Return a compact name -> description listing of all tools."""
    lines = []
    for t in tools:
        desc = (t.description or "").splitlines()[0][:max_desc_len]
        lines.append(f"- {t.name}: {desc}")
    return "\n".join(lines)
