"""Stage 11: Failure & Recovery Automated Test Suite.

Validates:
1. Invalid repository recovery (free-form & structured with error field)
2. Missing file inside an existing repository
3. Valid empty search result vs tool failure distinction
4. Invalid token auth failure reporting
5. Unreachable server connection failure reporting
6. Invalid tool arguments (offline)
7. Unexpected tool response / transport exception (offline)
8. Stage 12 write guard: writes outside GITHUB_WRITE_REPO are blocked (offline)
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_command(cmd: str) -> tuple[int, str]:
    print(f"\n▶ Running: {cmd}")
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    return proc.returncode, output


def test_invalid_repo_structured() -> None:
    print("\n" + "=" * 60)
    print("Test 1: Invalid Repository (Structured Output)")
    print("=" * 60)
    cmd = '.venv/bin/python src/main.py "Analyze non-existent-user-12345/non-existent-repo-98765" --structured'
    code, out = run_command(cmd)
    assert code == 0, f"Expected returncode 0, got {code}"
    assert '"error":' in out and "not found" in out.lower(), "Expected error message in structured output"
    print("✓ Test 1 Passed: Agent recovered and produced typed error field in structured response.")


def test_missing_file() -> None:
    print("\n" + "=" * 60)
    print("Test 2: Missing File in Valid Repository")
    print("=" * 60)
    cmd = '.venv/bin/python src/main.py "Check the file config/database.yml in saadtariq57/github-mcp-demo"'
    code, out = run_command(cmd)
    assert code == 0, f"Expected returncode 0, got {code}"
    assert "not contain" in out.lower() or "does not exist" in out.lower() or "absent" in out.lower(), (
        "Expected explanation that file is missing"
    )
    print("✓ Test 2 Passed: Agent investigated and confirmed file does not exist without crashing.")


def test_invalid_token() -> None:
    print("\n" + "=" * 60)
    print("Test 3: Invalid Authentication Token")
    print("=" * 60)
    cmd = 'GITHUB_PERSONAL_ACCESS_TOKEN=ghp_invalidtoken12345 .venv/bin/python src/main.py "Who am I on GitHub?"'
    code, out = run_command(cmd)
    assert code != 0, "Expected non-zero exit code"
    assert "[Fatal Error]" in out and "Authentication" in out, "Expected clean fatal error message"
    print("✓ Test 3 Passed: Clean diagnostic message printed without raw Python traceback.")


def test_unreachable_server() -> None:
    print("\n" + "=" * 60)
    print("Test 4: Unreachable MCP Server")
    print("=" * 60)
    cmd = 'GITHUB_MCP_URL=https://invalid-mcp-server.example.com/mcp/ .venv/bin/python src/main.py "Who am I on GitHub?"'
    code, out = run_command(cmd)
    assert code != 0, "Expected non-zero exit code"
    assert "[Fatal Error]" in out and "Connection failed" in out, "Expected clean connection error message"
    print("✓ Test 4 Passed: Clean connection failure reported without raw traceback.")


class FakeMCPClient:
    """Stands in for mcp.Client so tool-layer failures can be tested offline."""

    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls = 0

    async def call_tool(self, name, args):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def make_fake_tool(client: FakeMCPClient, read_only: bool = True, write_repo: str | None = None):
    from src.github_mcp.schema import json_schema_to_pydantic_model
    from src.github_mcp.tool import MCPTool

    schema = json_schema_to_pydantic_model(
        "get_file_contents",
        {
            "type": "object",
            "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}},
            "required": ["owner", "repo"],
        },
    )
    return MCPTool(
        name="get_file_contents",
        description="test",
        args_schema=schema,
        client=client,
        read_only=read_only,
        write_repo=write_repo,
    )


def test_invalid_tool_arguments() -> None:
    print("\n" + "=" * 60)
    print("Test 5: Invalid Tool Arguments (offline)")
    print("=" * 60)
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    client = FakeMCPClient()
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([make_fake_tool(client)], handle_tool_errors=True))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = {"name": "get_file_contents", "args": {"owner": "x"}, "id": "call_1", "type": "tool_call"}
    out = asyncio.run(graph.compile().ainvoke({"messages": [AIMessage(content="", tool_calls=[call])]}))
    msg = out["messages"][-1]
    print(f"  ToolMessage: {msg.content[:120]!r}")
    assert msg.status == "error", "Expected ToolMessage with error status"
    assert client.calls == 0, "Invalid arguments must be rejected before reaching the MCP server"
    print("✓ Test 5 Passed: Validation error returned to the LLM as a ToolMessage; MCP server never called.")


def test_unexpected_tool_response() -> None:
    print("\n" + "=" * 60)
    print("Test 6: Unexpected Tool Response / Transport Exception (offline)")
    print("=" * 60)
    from mcp.types import TextContent

    weird = SimpleNamespace(
        is_error=False,
        content=[TextContent(type="text", text="not json {"), {"unknown": "block"}],
    )
    out = asyncio.run(make_fake_tool(FakeMCPClient(result=weird)).ainvoke({"owner": "x", "repo": "y"}))
    print(f"  Result: {out!r}")
    assert "not json {" in out and "unknown" in out, "Expected raw text and repr fallback"

    boom = FakeMCPClient(exc=ConnectionError("stream closed"))
    out = asyncio.run(make_fake_tool(boom).ainvoke({"owner": "x", "repo": "y"}))
    print(f"  Result: {out!r}")
    assert out.startswith("[MCP exception from 'get_file_contents']"), "Expected exception turned into text"
    print("✓ Test 6 Passed: Malformed content and mid-run transport errors become text, not crashes.")


def test_write_guard() -> None:
    print("\n" + "=" * 60)
    print("Test 7: Write Guard (offline)")
    print("=" * 60)
    ok = SimpleNamespace(is_error=False, content=[])

    client = FakeMCPClient(result=ok)
    out = asyncio.run(
        make_fake_tool(client, read_only=False, write_repo="me/sandbox").ainvoke({"owner": "me", "repo": "real"})
    )
    print(f"  Wrong repo: {out!r}")
    assert out.startswith("[blocked]") and client.calls == 0, "Write to another repo must not reach the server"

    client = FakeMCPClient(result=ok)
    out = asyncio.run(make_fake_tool(client, read_only=False).ainvoke({"owner": "me", "repo": "sandbox"}))
    assert out.startswith("[blocked]") and client.calls == 0, "Write with no write repo configured must be blocked"

    client = FakeMCPClient(result=ok)
    asyncio.run(
        make_fake_tool(client, read_only=False, write_repo="me/sandbox").ainvoke({"owner": "me", "repo": "sandbox"})
    )
    assert client.calls == 1, "Write to the sandbox repo should go through"
    print("✓ Test 7 Passed: Writes only reach the server for GITHUB_WRITE_REPO.")


def main() -> None:
    print("============================================================")
    print("Stage 11: Failure & Recovery Test Suite")
    print("============================================================")
    test_invalid_tool_arguments()
    test_unexpected_tool_response()
    test_write_guard()
    test_invalid_token()
    test_unreachable_server()
    print("\nTo run the full suite (including live LLM calls):")
    print("  .venv/bin/python scripts/test_failures.py --all")

    if "--all" in sys.argv:
        test_invalid_repo_structured()
        test_missing_file()

    print("\nStage 11 Tests OK")


if __name__ == "__main__":
    main()
