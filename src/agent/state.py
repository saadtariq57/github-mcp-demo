"""State definitions for LangGraph agent."""

from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class State(TypedDict):
    """Conversation state storing message sequence and optional structured output."""
    messages: Annotated[list[AnyMessage], add_messages]
    structured_response: Optional[Any]
