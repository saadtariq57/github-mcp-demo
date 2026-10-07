"""Runner script for the GitHub MCP agent.

Delegates execution to the application entry point in `src.main`.

Usage:
  .venv/bin/python scripts/mcp_agent.py "Who am I on GitHub?"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.main import main

if __name__ == "__main__":
    main()
