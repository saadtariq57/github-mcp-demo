"""Human approval gate: pause the graph before any write tool runs."""

from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.types import Command, interrupt

from src.agent.state import State

REJECTED = "[rejected] The human did not approve this change. Nothing was written."


def make_approval_node(write_names: set[str]):
    """Return a node that sits between chatbot and tools.

    Read-only tool calls pass straight through. If the model asks for any write
    tool, the graph pauses (interrupt) with the proposed calls; the caller resumes
    it with True (run the tools) or False (answer every call with REJECTED).
    """

    def approval(state: State) -> Command[Literal["tools", "chatbot"]]:
        tool_calls = state["messages"][-1].tool_calls
        writes = [tc for tc in tool_calls if tc["name"] in write_names]
        if not writes:
            return Command(goto="tools")

        # Runs again from the top on resume; interrupt() then returns the human's answer.
        approved = interrupt({"proposed": [{"name": tc["name"], "args": tc["args"]} for tc in writes]})
        if approved:
            return Command(goto="tools")

        # Every tool call needs a ToolMessage reply, including reads in the same turn.
        rejections = [
            ToolMessage(content=REJECTED, tool_call_id=tc["id"], name=tc["name"]) for tc in tool_calls
        ]
        return Command(goto="chatbot", update={"messages": rejections})

    return approval
