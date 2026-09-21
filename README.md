# GitHub MCP Demo

A small learning project for understanding how an AI agent can interact with GitHub through the **Model Context Protocol (MCP)**.

This is an experimental project, not a production application.

## Goal

Understand the complete chain:

```text
User
  ↓
LangGraph Agent
  ↓
MCP Client
  ↓
GitHub MCP Server
  ↓
GitHub
```

The project should make it clear what each layer does and why it exists.

## What We Will Learn

* How MCP works
* MCP client/server architecture
* MCP tool discovery and schemas
* Calling MCP tools directly
* LangGraph state and agent loops
* LangGraph tool calling
* Using MCP tools inside LangGraph
* Multi-tool repository workflows
* Structured agent output
* Tool failures and recovery
* GitHub write operations
* Human approval before consequential actions
* Security considerations
* How these concepts can later map to the Gyrus agent

## Technology

* Python
* LangGraph
* LangChain
* GitHub MCP Server
* GitHub

## Important Principle

Do **not** recreate GitHub API functionality manually unless the experiment specifically requires it.

The purpose is to understand and use the GitHub MCP Server as the capability layer.

## Project Philosophy

Keep the project:

* Small
* Explicit
* Easy to debug
* Easy to understand
* Incremental

Do not introduce production-level architecture, unnecessary abstractions, databases, queues, or deployment infrastructure unless a stage specifically requires them.

Follow `PLAN.md` in order.
