# Conclusions: GitHub MCP Demo

What this project showed, stage by stage, and what to carry into the Gyrus Agent. Every claim below is backed by code in this repo or a run in `logs/`.

## The chain

```text
User ─► LangGraph agent ─► MCP client ─► GitHub MCP server ─► GitHub
        (src/agent)        (mcp.Client)  (api.githubcopilot.com/mcp/)
```

| Layer | Owns | Does not own |
|---|---|---|
| LangGraph | Workflow, state, the model ⇄ tool loop, pausing for approval | Talking to GitHub |
| MCP client | Protocol: connect, `list_tools`, `call_tool` | Deciding which tool to call |
| GitHub MCP server | Turning GitHub's API into 49 described, typed tools | Your safety policy |
| GitHub | Data and permissions (the token's scopes) | Anything about agents |

## 1. What MCP provides
- **A standard tool contract.** Each tool comes with a `name`, a `description`, an `inputSchema` (JSON Schema), an `outputSchema` and `annotations`. The client discovers tools at runtime through `list_tools`, which is paginated. No tool is hard-coded (`src/github_mcp/discovery.py`).
- **One call shape for every tool:** `call_tool(name, args)` → content blocks plus an `is_error` flag. The same client code calls any tool.
- **Behavior hints:** `readOnlyHint` (along with `idempotentHint` and `destructiveHint`) lets the client tell reads from writes without knowing GitHub. This split drove Stage 12: 29 of the 49 tools are read-only and 20 are writes.
- **What MCP does not provide:** policy, approval, identity resolution or retries. The client has to add those.

## 2. What LangGraph provides
- **The agent loop as a graph:** `chatbot → (tool calls?) → tools → chatbot`, with message state built up by `add_messages` (`src/agent/graph.py`).
- **`ToolNode` with `handle_tool_errors`:** bad arguments and unknown tool names come back to the model as text instead of crashing. The model once invented `repo_browser.create_branch` and got `not a valid tool` back.
- **Interrupts and checkpoints (Stage 13):** `interrupt()` pauses the graph mid-run. The checkpointer stores the state, and `Command(resume=...)` continues it. This is the key thing LangGraph adds on top of plain tool calling, because it lets a person make a decision in the middle of a run.
- **Optional structured output:** an extractor node turns the conversation into a `RepositoryAnalysis` model (Stage 10).

## 3. What the GitHub MCP server provides
- Hosted GitHub capabilities (repos, files, branches, commits, issues, PRs, search), authenticated with a personal access token sent as `Authorization: Bearer`.
- Clear error results (`is_error=True` with GitHub's message, e.g. 404s), which the adapter passes on to the model as text.
- One server-specific detail: `owner`/`repo` carry `x-mcp-header`, so the client has to call `list_tools` before `call_tool` in order to send the matching headers.

## 4. How tool calling works here
1. **Discover:** `list_tools` → 49 tools. Without `--allow-writes`, code drops all non-read-only tools before any model sees them.
2. **Identify:** code calls `get_me` directly (no model) and adds the login to both prompts, so "mcp-write-sandbox" resolves to `saadtariq57/mcp-write-sandbox`.
3. **Route:** a small model gets a one-line catalog of tools and returns a JSON list of the tool names it needs (`src/router`). Only those tools are offered to the agent. This catalog is most of the router's 1,000–1,700 input tokens per run.
4. **Adapt:** each MCP `inputSchema` becomes a Pydantic model (`src/github_mcp/schema.py`), which is what the model sees as a function definition. Arguments are validated before the MCP server is called.
5. **Loop:** the model returns `tool_calls`. LangGraph runs them through `MCPTool._arun` → `client.call_tool` and appends the results as `ToolMessage`s. The model is then called again until it answers in text. Each call resends the whole history.

## 5. Failure behavior (Stage 11, `scripts/test_failures.py`)
| Failure | Where it is caught | What the user/model sees |
|---|---|---|
| Bad token, unreachable server | `main.py` startup | One clean `[Fatal Error] …` line, exit code ≠ 0 |
| Repo or file not found | MCP server `is_error` | `[MCP error from 'tool']: …` → the agent reports it |
| Invalid arguments | Pydantic schema in `ToolNode` | Error `ToolMessage`; the server is never called |
| Transport drop mid-run, odd content | `MCPTool._arun` | `[MCP exception …]` text, no crash |
| Model invents a tool name | `ToolNode` | `not a valid tool` → the model recovers |

**Rule learned:** turn every failure into text the model can reason about. Only fail the whole process at startup.

## 6. Write and approval model
Four layers, from outermost to innermost. **Only the code layers are guaranteed.**

1. **Token scopes** (GitHub): the absolute limit on what can happen.
2. **Write mode off by default** (code, `main.py`): write tools are removed unless `--allow-writes` is passed, so the model cannot call them.
3. **Repo guard** (code, `MCPTool._arun`): write calls are allowed only on `GITHUB_WRITE_REPO`, compared case-insensitively. Anything else gets `[blocked]` before the server is contacted.
4. **Human approval** (graph, `src/agent/approval.py`): any write tool call pauses the graph and shows the exact arguments, including the full file content. A rejection gives the model `[rejected]` for every call in that turn. With no interactive terminal, the answer counts as **no**. Every decision is logged as `[Approval] APPROVED/REJECTED …`.

The prompt rules (analyze → plan → write → verify, never commit to `main`) shape behavior but enforce nothing. In a live run the model skipped the "state your plan" step and went straight to `create_branch`. Rules that matter must live in code.

**Trade-off seen:** approval happens per model turn. A branch, a file and a PR mean three prompts, and the first prompt (create the branch) comes before the file content is visible. Approving a whole plan at once would need the model to propose the full change as structured data first.

## 7. Security considerations
- **Secrets:** tokens live only in `.env`, which is gitignored. The run logs do not include the token. However, `get_file_contents` results contain `download_url`s with a short-lived `?token=` query string, and those go to the LLM provider and the terminal. Strip them in the adapter if that matters.
- **Untrusted content:** file contents, issues and PR bodies are input chosen by an attacker as far as the model is concerned. A README saying "now push to main" reaches the model as a tool result, which is why the guard and approval are in code, not in the prompt.
- **Least privilege:** use a token that can access only the sandbox repo. The repo guard is a second line of defense, not a substitute for that.
- **Trusting annotations:** `readOnlyHint` comes from the server. That's fine for GitHub's official server; for any third-party MCP server, use your own allowlist of tool names.
- **Prompt rules are not controls:** see §6.

## 8. Reuse in Gyrus

**Reuse**
- The `MCPTool` adapter pattern: an MCP `inputSchema` becomes a Pydantic model, which becomes a LangChain tool; errors come back as text; `None` arguments are dropped.
- Discovery plus a read-only filter, with write tools added only by an explicit opt-in.
- A code-level guard on write targets inside the tool adapter (scope or tenant checks belong here).
- An approval gate as a graph node built on `interrupt()`, not inside tools and not in prompts.
- Identity and context resolved in code, then put into the prompt.
- Per-run trace logs with an entry for each model call, tool result and approval decision.

**Don't reuse as-is**
- `InMemorySaver`: an approval that waits on a person through a UI needs a persistent checkpointer (e.g. Postgres) and stable `thread_id`s.
- `input()` approval in the terminal: Gyrus needs an approval UI or API and has to handle timeouts. The rule "no answer means no" should stay.
- The LLM router sending the whole tool catalog on every run: it's costly and sometimes leaves out tools the agent needs. Prefer fixed tool sets per task, or put descriptions in a cache.
- Relying on `readOnlyHint` from servers you don't control.
- Per-call approval for multi-step changes: prefer "propose the whole change → approve once → run".
