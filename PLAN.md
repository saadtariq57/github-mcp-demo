# Project Plan

The project is built incrementally. Each stage should be completed and understood before moving to the next one.

---

## Stage 1 — Project Setup

Create the basic Python project.

### Tasks

* Initialize project
* Create virtual environment
* Install required dependencies
* Create basic project structure
* Configure environment variables
* Configure Git
* Add `.gitignore`
* Verify Python environment

### Result

A clean, runnable project with configuration ready for MCP experimentation.

---

## Stage 2 — Understand GitHub MCP

Before writing integration code, understand what we are connecting to.

### Learn

* What MCP is
* MCP client vs server
* What an MCP tool is
* Tool schemas
* How GitHub MCP Server exposes GitHub capabilities
* Where GitHub authentication fits

### Result

Clear understanding of the architecture before implementation.

---

## Stage 3 — Connect to MCP Server

Create the smallest possible MCP client.

### Tasks

* Start/connect to GitHub MCP Server
* Establish MCP session
* Verify communication
* Keep LangGraph out of this stage

### Result

```text
Python MCP Client → GitHub MCP Server
```

Communication works independently of any agent framework.

---

## Stage 4 — Discover MCP Tools

Use MCP's tool discovery mechanism.

### Tasks

* List available tools
* Inspect names
* Inspect descriptions
* Inspect input schemas
* Understand what each tool expects

### Result

We understand the capabilities exposed by the MCP server rather than guessing them.

---

## Stage 5 — Manually Invoke a Tool

Directly call a safe read-only GitHub tool from Python.

### Understand

```text
Python
  ↓
MCP request
  ↓
MCP Server
  ↓
GitHub
  ↓
MCP result
  ↓
Python
```

### Result

A working end-to-end MCP tool invocation without an LLM.

---

## Stage 6 — Introduce LangGraph

Build a minimal LangGraph application independently.

### Learn

* Graph state
* Nodes
* Edges
* Model interaction
* Agent loop
* Tool execution concept

Do not connect GitHub MCP yet.

### Result

A basic LangGraph agent whose behavior is understood independently.

---

## Stage 7 — Connect MCP Tools to LangGraph

Make MCP tools available to the LangGraph agent.

### Understand

* How an MCP tool becomes an agent capability
* How the model decides to call a tool
* How tool results return to the agent
* Boundary between LangGraph and MCP

### Result

```text
User
 ↓
LangGraph
 ↓
MCP Tool
 ↓
GitHub MCP Server
 ↓
GitHub
```

---

## Stage 8 — Multi-tool Experiment

Test tasks requiring multiple GitHub tools.

For example:

```text
Find repository
  ↓
Inspect repository
  ↓
Inspect files
  ↓
Read relevant files
```

### Learn

* Multiple tool calls
* Tool sequencing
* Agent reasoning between calls
* Passing information from one tool call to another

---

## Stage 9 — Repository Analysis

Build a useful repository-analysis workflow.

The agent should be able to inspect a repository and answer questions based on its actual contents.

Examples:

* What technologies does this repository use?
* What is the project structure?
* Where is the application entry point?
* How is the project built?
* Where is CI/CD configuration?
* What files are relevant to deployment?

The goal is not to build a perfect analyzer. The goal is to understand an agent performing a real multi-step GitHub task.

---

## Stage 10 — Structured Output

Introduce reliable structured responses.

The agent should produce machine-consumable information instead of only free-form text.

Example:

```text
RepositoryAnalysis
├── language
├── framework
├── package_manager
├── entry_points
├── build_command
├── test_command
└── deployment_files
```

### Result

Understand why structured output matters when an agent becomes part of a larger software system.

---

## Stage 11 — Failure & Recovery

Intentionally test failures.

### Cases

* Invalid repository
* Missing file
* Invalid tool arguments
* Permission failure
* MCP connection failure
* GitHub API failure
* Unexpected tool response

Also distinguish:

```text
Valid empty result
        ≠
Tool failure
```

### Result

Understand how failures propagate through the system and how an agent should react.

---

## Stage 12 — GitHub Write Operations

Introduce controlled write operations.

Examples:

* Create branch
* Modify/create a file
* Commit changes
* Create a pull request

Use a dedicated test repository.

Start with direct controlled calls before allowing the agent to perform writes autonomously.

### Result

Understand the difference between read-only agent capabilities and consequential actions.

---

## Stage 13 — Human Approval & Final Experiment

Add explicit approval before consequential GitHub actions.

Final workflow:

```text
User Request
    ↓
Repository Analysis
    ↓
Agent Plan
    ↓
Proposed Change
    ↓
Human Approval
    ↓
GitHub Write
    ↓
Verification
```

Then document the final conclusions:

* What MCP provides
* What LangGraph provides
* What the MCP server provides
* How tool calling works
* Failure behavior
* Write/approval model
* Security considerations
* What should and should not be reused in Gyrus

This stage produces the final architectural understanding that will be transferred to the Gyrus Agent.
