# Human Approval Flow: End to End

This walks one real request through the code, from the command you type to the GitHub write, with the actual code that runs at each step. All snippets are copied from the repo. `...` marks lines left out because they don't matter for this flow.

## The example request

```bash
.venv/bin/python src/main.py --allow-writes \
  "In mcp-write-sandbox, create a branch demo-1, add notes/demo.md saying 'hello', and open a PR into main"
```

`.env` contains `GITHUB_WRITE_REPO=saadtariq57/mcp-write-sandbox`.

## The whole picture

```text
 main.py                                 graph (LangGraph)                       GitHub
 ───────                                 ─────────────────                       ──────
 1 parse args, load .env
 2 connect MCP, list 49 tools
 3 get_me → "saadtariq57"
 4 Gate 1: keep write tools? (--allow-writes)
 5 wrap tools as MCPTool(read_only, write_repo)
 6 router LLM picks tools
 7 build_graph ───────────────────────►  chatbot ─► approval ─► tools ─► chatbot ...
 8 app.ainvoke(question) ──────────────►  chatbot: model reads repo
                                          approval: read-only → pass
                                          tools: get_file_contents ───────────►  read
                                          chatbot: model asks create_branch
                                          approval: WRITE → interrupt() ⏸
 9 result has "__interrupt__" ◄─────────  (state saved in InMemorySaver)
10 print proposal, ask [y/N]
11 app.ainvoke(Command(resume=True)) ──►  approval runs again, interrupt() → True
                                          tools: create_branch
                                            MCPTool Gate 2: repo == sandbox? ─►  write
                                          chatbot: next write → interrupt() ⏸
   ... loop 9–11 for each write ...
12 no "__interrupt__" → done, finalize log
```

There are three checks, all of them code:

| Check | Decides | Where |
|---|---|---|
| Gate 1: write mode | Whether write tools exist at all | `main.py`, before routing |
| **Approval step** | Whether this write runs | `src/agent/approval.py` |
| Gate 2: repo guard | Which repo a write may touch | `src/github_mcp/tool.py` |

---

## Step 1: Parse arguments and load config
**`src/main.py`**

```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitHub MCP Agent runner.")
    parser.add_argument("question", nargs="?", default="Who am I on GitHub?", ...)
    ...
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Expose write tools (limited to GITHUB_WRITE_REPO)",
    )
    ...

def main() -> None:
    args = parse_args()
    asyncio.run(run(args.question, structured=args.structured,
                    allow_writes=args.allow_writes, show_prompts=args.show_prompts))
```

`run()` reads `.env`. With writes on, a sandbox repo is required:

```python
    write_repo = os.getenv("GITHUB_WRITE_REPO", "").strip() or None
    if allow_writes and not write_repo:
        print("--allow-writes needs GITHUB_WRITE_REPO=owner/repo in .env")
        sys.exit(1)
```

**State now:** `allow_writes=True`, `write_repo="saadtariq57/mcp-write-sandbox"`.

---

## Step 2: Connect to MCP and discover tools
**`src/main.py`** → **`src/github_mcp/discovery.py`**

```python
            async with Client(transport) as mcp_client:
                ...
                mcp_tools = await list_all_mcp_tools(mcp_client)
```

```python
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
```

Each tool comes from the server with an annotation saying whether it writes:

```json
{ "name": "create_branch",     "annotations": { "readOnlyHint": false } }
{ "name": "get_file_contents", "annotations": { "readOnlyHint": true  } }
```

**State now:** 49 MCP tools (29 read-only, 20 write).

---

## Step 3: Resolve who you are (code, no model)
**`src/main.py`** → **`src/github_mcp/identity.py`**

```python
                login = await get_authenticated_login(mcp_client)
```

```python
async def get_authenticated_login(client: Client) -> str | None:
    """Return the token owner's login via get_me, or None if it can't be read."""
    try:
        result = await client.call_tool("get_me", {})
        if result.is_error:
            return None
        return json.loads(extract_mcp_text(result.content)).get("login")
    except Exception:
        return None
```

**State now:** `login="saadtariq57"`, so "mcp-write-sandbox" can become `saadtariq57/mcp-write-sandbox`.

---

## Step 4: Gate 1, write mode
**`src/main.py`** + **`src/github_mcp/discovery.py`**

```python
                # Read-only by default: write tools are dropped before routing, so the LLM never sees them.
                if allow_writes:
                    print(f"Write mode: enabled (repo {write_repo})")
                else:
                    mcp_tools = [t for t in mcp_tools if is_read_only(t)]
                    print(f"Write mode: disabled ({len(mcp_tools)} read-only tools kept)")
```

```python
def is_read_only(mcp_tool: Tool) -> bool:
    """True when the server annotates the tool as read-only (readOnlyHint)."""
    return bool(mcp_tool.annotations and mcp_tool.annotations.read_only_hint)
```

We passed `--allow-writes`, so all 49 tools stay. Without it, `create_branch` would be removed here and the model could never call it.

---

## Step 5: Wrap each tool as an `MCPTool`
**`src/main.py`** → **`src/github_mcp/discovery.py`**

```python
                lc_tools = make_langchain_tools(mcp_tools, mcp_client, write_repo=write_repo)
```

```python
            MCPTool(
                name=mcp_tool.name,
                description=mcp_tool.description or mcp_tool.name,
                args_schema=schema,
                client=client,
                read_only=is_read_only(mcp_tool),   # create_branch → False
                write_repo=write_repo,              # "saadtariq57/mcp-write-sandbox"
            )
```

Each tool now carries its own `read_only` flag and the one repo it may write to. Both are used later.

---

## Step 6: The router model picks the tools
**`src/main.py`** → **`src/router/router.py`**

```python
                selected_names = await route_tools(
                    question=question,
                    mcp_tools=mcp_tools,
                    api_key=api_key,
                    router_model=router_model,
                    logger=logger,
                    login=login,
                )
                filtered_tools = [t for t in lc_tools if t.name in set(selected_names)]
```

The router prompt has a rule for write requests:

```text
- Write requests: If the question explicitly asks to create a branch, create/modify a file, commit,
  or open a pull request, include the matching write tools (...). Also include "get_file_contents"
  (to analyze before and verify after) and, when a pull request is opened, "pull_request_read".
```

**State now:** `filtered_tools = [create_branch, create_or_update_file, create_pull_request, get_file_contents, pull_request_read]`.

---

## Step 7: Build the graph with the approval step
**`src/agent/graph.py`**

```python
    model = ChatOpenAI(model=model_name, ...).bind_tools(tools)   # the model may call only these tools

    def chatbot(state: State) -> dict:
        response = model.invoke(state["messages"])
        ...
        return {"messages": [response]}

    _tool_node = ToolNode(tools, handle_tool_errors=True)

    async def tools_with_logging(state: State) -> dict:
        """Run tools and log a concise summary of each result."""
        result = await _tool_node.ainvoke(state)
        ...
        return result

    # Write tools (MCPTool.read_only == False) must pass the human approval gate.
    write_names = {t.name for t in tools if not getattr(t, "read_only", True)}

    graph = StateGraph(State)
    graph.add_node("chatbot", chatbot)
    graph.add_node("approval", make_approval_node(write_names))
    graph.add_node("tools", tools_with_logging)

    graph.add_edge(START, "chatbot")
    graph.add_edge("tools", "chatbot")
    ...
        graph.add_conditional_edges("chatbot", tools_condition, {"tools": "approval", END: END})

    # A checkpointer saves state while the graph is paused at the approval interrupt.
    return graph.compile(checkpointer=InMemorySaver())
```

What this sets up:
- `write_names = {"create_branch", "create_or_update_file", "create_pull_request"}`.
- `tools_condition` checks whether the model's last message has tool calls. If yes, the graph goes to `approval`, **never directly to `tools`**. If no, it goes to `END`.
- `InMemorySaver` is what makes pausing possible: the graph's state is stored under a `thread_id` and can be resumed later.

```text
START → chatbot ──has tool calls──► approval ──approved / read-only──► tools ──► chatbot
           │                            │
           └──no tool calls──► END      └──rejected──► chatbot
```

---

## Step 8: The approval step
**`src/agent/approval.py`**

This is the core of Stage 13:

```python
REJECTED = "[rejected] The human did not approve this change. Nothing was written."


def make_approval_node(write_names: set[str]):
    def approval(state: State) -> Command[Literal["tools", "chatbot"]]:
        tool_calls = state["messages"][-1].tool_calls
        writes = [tc for tc in tool_calls if tc["name"] in write_names]
        if not writes:
            return Command(goto="tools")                                   # (A) reads pass straight through

        # Runs again from the top on resume; interrupt() then returns the human's answer.
        approved = interrupt({"proposed": [{"name": tc["name"], "args": tc["args"]} for tc in writes]})   # (B)
        if approved:
            return Command(goto="tools")                                   # (C) approved → run the tools

        # Every tool call needs a ToolMessage reply, including reads in the same turn.
        rejections = [
            ToolMessage(content=REJECTED, tool_call_id=tc["id"], name=tc["name"]) for tc in tool_calls
        ]
        return Command(goto="chatbot", update={"messages": rejections})    # (D) rejected → skip tools

    return approval
```

The key behavior is `interrupt()`, which acts differently on its first and second call:
- **First time:** it stops the graph and saves its state. `app.ainvoke(...)` returns to `main.py` with `result["__interrupt__"]` holding the `{"proposed": ...}` value.
- **After `Command(resume=X)`:** LangGraph runs `approval` **again from its first line**. This time `interrupt()` doesn't stop; it **returns `X`**, so `approved` becomes your answer.

---

## Step 9: Start the run
**`src/main.py`**

```python
                system_prompt = AGENT_SYSTEM + (IDENTITY_CONTEXT.format(login=login) if login else "")
                ...
                config = {"configurable": {"thread_id": logger.log_path.stem}}
                result = await app.ainvoke(
                    {"messages": [SystemMessage(content=system_prompt), HumanMessage(content=question)]},
                    config,
                )
```

`thread_id` is the key the paused state is saved under. Resuming has to use the same `config`.

### What happens inside the graph during this `ainvoke`

**Turn 1:** `chatbot` asks the model. It reads first, as the prompt asks:
```text
AIMessage tool_calls: [get_file_contents(owner="saadtariq57", repo="mcp-write-sandbox", path="")]
```
→ `approval`: `get_file_contents` isn't in `write_names` → branch **(A)** → `tools` runs it:

**`src/github_mcp/tool.py`**, `MCPTool._arun` (read, so the guard is skipped):
```python
        if not self.read_only:
            ...                                      # skipped: read_only is True
        try:
            result = await self.client.call_tool(self.name, filtered)   # → MCP → GitHub (read)
```
```text
ToolMessage (get_file_contents): [ { "name": "README.md", ... } ]
```

**Turn 2:** `chatbot` again. Now the model asks for a write:
```text
AIMessage tool_calls: [create_branch(owner="saadtariq57", repo="mcp-write-sandbox", branch="demo-1")]
```
→ `approval`: `create_branch` **is** in `write_names` → branch **(B)** → `interrupt(...)`. ⏸ **The graph stops.**

`ainvoke` returns. The `result` dict looks like:
```python
{
  "messages": [SystemMessage, HumanMessage, AIMessage(get_file_contents), ToolMessage, AIMessage(create_branch)],
  "__interrupt__": [Interrupt(value={"proposed": [
      {"name": "create_branch", "args": {"owner": "saadtariq57", "repo": "mcp-write-sandbox", "branch": "demo-1"}}
  ]})]
}
```

Nothing has been written to GitHub yet.

---

## Step 10: The human-in-the-loop loop
**`src/main.py`**

```python
                printed = 0
                while True:
                    _print_messages(result["messages"][printed:])        # show what the agent did so far
                    printed = len(result["messages"])
                    if "__interrupt__" not in result:                    # graph finished → leave loop
                        break
                    proposed = result["__interrupt__"][0].value["proposed"]
                    approved = _ask_approval(proposed)                   # ask the human
                    logger.record_approval(approved, [c["name"] for c in proposed])
                    result = await app.ainvoke(Command(resume=approved), config)   # resume the graph
```

`_ask_approval` shows every argument (the full file content for file writes) and reads your answer:

```python
def _ask_approval(proposed: list[dict]) -> bool:
    """Show the proposed write calls and ask the human. Non-interactive → no."""
    print("\n" + "=" * 60)
    print("APPROVAL REQUIRED — the agent wants to make these GitHub writes:")
    print("=" * 60)
    for i, call in enumerate(proposed, 1):
        args = dict(call["args"])
        content = args.pop("content", None)
        print(f"{i}. {call['name']}")
        for key, value in args.items():
            print(f"     {key}: {value}")
        if content is not None:
            print("     content:")
            for line in str(content).splitlines():
                print(f"       | {line}")
    print("=" * 60)
    if not sys.stdin.isatty():
        print("No interactive terminal — treating as NOT approved.")
        return False
    answer = input("Approve these GitHub writes? [y/N] ").strip().lower()
    return answer in ("y", "yes")
```

Only `y` / `yes` approves. `n`, Enter, anything else, or no terminal at all means **rejected**.

What you see in the terminal:
```text
AIMessage: tool_call → get_file_contents({"owner": "saadtariq57", "repo": "mcp-write-sandbox", "path": ""})
ToolMessage (get_file_contents):
[ ... README.md ... ]
AIMessage: tool_call → create_branch({"owner": "saadtariq57", "repo": "mcp-write-sandbox", "branch": "demo-1"})

============================================================
APPROVAL REQUIRED — the agent wants to make these GitHub writes:
============================================================
1. create_branch
     owner: saadtariq57
     repo: mcp-write-sandbox
     branch: demo-1
============================================================
Approve these GitHub writes? [y/N]
```

---

## Step 11a: You answer `y` (approved)

`main.py` calls `app.ainvoke(Command(resume=True), config)`. LangGraph loads the saved state and runs `approval` again:

```python
        approved = interrupt({...})     # now returns True instead of pausing
        if approved:
            return Command(goto="tools")   # (C)
```

`tools` runs `create_branch` → **`MCPTool._arun`**, where Gate 2 runs:

```python
    async def _arun(self, **kwargs: Any) -> str:
        # Strip None values — optional params must be omitted, not sent as null.
        filtered = {k: v for k, v in kwargs.items() if v is not None}

        # Write guard: block before the call ever reaches the MCP server.
        if not self.read_only:
            target = f"{filtered.get('owner')}/{filtered.get('repo')}"
            if not self.write_repo or target.lower() != self.write_repo.lower():
                return (
                    f"[blocked] {self.name!r} is a write tool; writes are only allowed on "
                    f"{self.write_repo or '(no write repo configured)'}, not {target}."
                )

        try:
            result = await self.client.call_tool(self.name, filtered)   # ← the real GitHub write
        except Exception as exc:
            return f"[MCP exception from {self.name!r}]: {type(exc).__name__}: {exc}"
```

`saadtariq57/mcp-write-sandbox` equals `write_repo`, so the call goes through: MCP server → GitHub creates the branch:
```text
ToolMessage (create_branch): { "ref": "refs/heads/demo-1", "object": { "sha": "...", "type": "commit" } }
```

The edge `tools → chatbot` goes back to the model, which asks for the **next** write:
```text
AIMessage tool_calls: [create_or_update_file(path="notes/demo.md", content="hello", branch="demo-1", ...)]
```
→ `approval` → `interrupt()` ⏸ → back in the `while` loop in `main.py`, which asks again, this time showing the file content:
```text
1. create_or_update_file
     owner: saadtariq57
     repo: mcp-write-sandbox
     path: notes/demo.md
     branch: demo-1
     message: Add notes/demo.md
     content:
       | hello
Approve these GitHub writes? [y/N]
```
The same happens for `create_pull_request`. Each write is a separate pause and a separate decision. After the last write, the model verifies (`get_file_contents` with `ref=refs/heads/demo-1`, `pull_request_read`), and those reads pass straight through **(A)**.

## Step 11b: You answer `n` (rejected)

`main.py` calls `app.ainvoke(Command(resume=False), config)`. `approval` runs again:

```python
        approved = interrupt({...})     # returns False
        if approved:                    # skipped
            ...
        rejections = [
            ToolMessage(content=REJECTED, tool_call_id=tc["id"], name=tc["name"]) for tc in tool_calls
        ]
        return Command(goto="chatbot", update={"messages": rejections})   # (D)
```

- The `tools` step is **never entered**, so `MCPTool._arun` never runs and **nothing reaches GitHub**.
- The model still needs a result for each tool call it made, so the code adds a fake one: `"[rejected] The human did not approve this change. Nothing was written."`
- The flow goes back to `chatbot`. The prompt rule ("A "[rejected]" tool result means the human did not approve. Stop, report that nothing was changed, and do not retry.") makes the model finish with a text answer. With no tool calls, the graph goes to `END`.

Real output from a rejected run (`logs/2026-10-27_23-49-53.log`):
```text
ToolMessage (create_branch):
[rejected] The human did not approve this change. Nothing was written.
AIMessage: The request to create a new branch **`approval-test`**, add the file `docs/approval-test.md`,
and open a pull request was not approved.

**Result:** No changes were made to the repository.
```

If the model ignored the rule and asked again, it would just hit `approval` again and you'd be asked again. The rule only shapes the wording; the code is what actually stops the write.

---

## Step 12: Finish

When the model answers with plain text (no tool calls), `tools_condition` sends the graph to `END`. `ainvoke` returns **without** `__interrupt__`, the `while` loop exits, and the log is finished:

```python
                    if "__interrupt__" not in result:
                        break
                ...
                logger.finalize()
```

The log records every step, including your decisions:
```text
[Identity]  get_me (code, not LLM) → saadtariq57
[Router]    input= 1,658  output=    20  total= 1,678
[Call  1]  get_file_contents(path="")                            in= 1,499  out=   137
           ↳ dir: 1 entries (README.md)
[Call  2]  create_branch(owner=saadtariq57, repo=mcp-write-sandbo)  in= 1,739  out=   173
[Approval]  REJECTED create_branch
[Call  3]  [response]                                            in= 1,807  out=   131
```

---

## Message history at each point (approve path)

| After | `state["messages"]` ends with | Next step |
|---|---|---|
| Start | `HumanMessage(question)` | `chatbot` |
| Turn 1 | `AIMessage(get_file_contents)` | `approval` → (A) `tools` |
| Read done | `ToolMessage(README.md…)` | `chatbot` |
| Turn 2 | `AIMessage(create_branch)` | `approval` → ⏸ **pause** |
| Resume `True` | same | `approval` → (C) `tools` → GitHub |
| Write done | `ToolMessage(refs/heads/demo-1)` | `chatbot` |
| Turn 3 | `AIMessage(create_or_update_file)` | `approval` → ⏸ **pause** |
| … | … | … |
| Final | `AIMessage("Created branch… PR #…")` | `END` |

## Where to put a breakpoint

| To see… | Break at |
|---|---|
| The tool list after Gate 1 | `src/main.py`, the line after `if allow_writes:` |
| What the model asked for | `src/agent/approval.py`, `writes = [...]` |
| The pause and the resume | `src/agent/approval.py`, `approved = interrupt(...)` (hit twice per write) |
| Your answer coming in | `src/main.py`, `result = await app.ainvoke(Command(resume=approved), config)` |
| The actual GitHub call | `src/github_mcp/tool.py`, `result = await self.client.call_tool(...)` |
