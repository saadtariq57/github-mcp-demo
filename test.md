**Repository Overview**

| Item | Location | Purpose |
|------|----------|---------|
| **Entry‑point script** | `scripts/mcp_agent.py` | Main program that wires the GitHub MCP client to a LangGraph agent and runs the demo question. |
| **Build / run instructions** | `requirements.txt` (plus the repository README) | Lists the Python packages needed; the README explains the intended virtual‑environment workflow. |
| **Supporting code** | `scripts/` (other helper scripts) | `connect.py`, `discover.py`, `invoke.py`, `langgraph_demo.py`, `verify_env.py` – utilities used by the demo but not the primary entry point. |
| **Source package** | `src/` (currently empty) | Placeholder for a Python package; not required for the demo run. |

---

## 1️⃣ Entry Point

The demo is launched from **`scripts/mcp_agent.py`**.  
Key evidence:

* The file contains a `run()` coroutine that performs the full flow (connect to MCP, discover tools, build a LangGraph graph, ask a question, print results).  
* At the bottom of the file you can see the classic “script‑guard”:

```python
if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Who am I on GitHub?"
    asyncio.run(run(question))
```

* The file’s header comment (`"""Stage 7: connect GitHub MCP tools to a LangGraph agent…`​) explains that this script is the *stage‑7* entry point for the demo.

Source excerpt (truncated for brevity) – **`scripts/mcp_agent.py`**【source=functions.get_file_contents&path=scripts/mcp_agent.py】:

```python
...
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(question: str) -> None:
    ...
    # 1. Discover tools and wrap them.
    # 2. Build and run the graph.
    # 3. Print the conversation transcript.
    ...

if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Who am I on GitHub?"
    asyncio.run(run(question))
```

Running this script (`python scripts/mcp_agent.py`) is the way to start the demo.

---

## 2️⃣ Build / Setup Steps

The project is a **pure‑Python** demo. No compiled code, Dockerfile, or CI workflow is present, so the build process is just dependency installation and environment preparation.

### a. Prerequisites

| Requirement | Reason |
|-------------|--------|
| Python 3.9+ (any recent version) | All source files are plain Python; the `requirements.txt` pins versions that work with recent interpreters. |
| Git (to clone the repo) | Standard for obtaining the source. |
| Optional: `make` (if you want a one‑liner) | Not provided out‑of‑the‑box, but a typical developer might add a `make install` target. |

### b. Install dependencies

1. **Create a virtual environment** (recommended, matches the README’s example):

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # on Windows: .venv\Scripts\activate
   ```

2. **Install the pinned packages**:

   ```bash
   pip install -r requirements.txt
   ```

   The `requirements.txt` file lists the exact libraries needed:

   ```text
   mcp==2.2.0
   python-dotenv==1.2.3
   langgraph==1.2.12
   langchain-core==1.6.6
   langchain-openai==1.6.7
   ```

   (File content – **`requirements.txt`**【source=functions.get_file_contents&path=requirements.txt】)

### c. Configure runtime secrets

The demo expects two environment variables (see the top of `scripts/mcp_agent.py`):

| Variable | Description | Where to set |
|----------|-------------|--------------|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub token with repo‑read/write scopes | Add to a `.env` file (the repo ships a `.env.example`). |
| `OPENROUTER_API_KEY` | API key for the LLM provider used by LangChain | Also placed in `.env`. |
| `OPENROUTER_MODEL` (optional) | Model name (defaults to `openai/gpt-4o-mini`). |
| `GITHUB_MCP_URL` (optional) | URL of the GitHub MCP server (defaults to `https://api.githubcopilot.com/mcp/`). |

The `.env.example` file shows the required keys (its presence is listed in the root directory). Load them with `python-dotenv` – the script already calls `load_dotenv(ROOT / ".env")`.

### d. Run the demo

```bash
# From the repository root:
.venv/bin/python scripts/mcp_agent.py               # defaults to "Who am I on GitHub?"
# Or pass a custom question:
.venv/bin/python scripts/mcp_agent.py "List branches in saadtariq57/github-mcp-demo"
```

The script will:

1. Open an MCP session (`Client` → `streamable_http_client`).  
2. Page through `tools/list` to discover every GitHub MCP tool.  
3. Dynamically create LangChain `BaseTool` wrappers for each MCP tool.  
4. Build a LangGraph state‑machine graph that can invoke those tools.  
5. Submit the user question, let the model decide which tool(s) to call, and print the final conversation transcript.

---

## 3️⃣ Summary

| Topic | Answer |
|-------|--------|
| **Entry point** | `scripts/mcp_agent.py` – executed with `python scripts/mcp_agent.py`. |
| **Build/setup** | 1. Create a virtualenv. <br>2. `pip install -r requirements.txt`. <br>3. Populate a `.env` file (based on `.env.example`) with `GITHUB_PERSONAL_ACCESS_TOKEN` and `OPENROUTER_API_KEY`. <br>4. Run the entry‑point script. |

No additional build artefacts (Dockerfile, Makefile, CI workflows) exist in the repository, so the above steps constitute the full setup required to get the demo running.
--- 