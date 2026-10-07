"""State definitions for LangGraph agent."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class State(TypedDict):
    """Conversation state storing message sequence."""
    messages: Annotated[list[AnyMessage], add_messages]
