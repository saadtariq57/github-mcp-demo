"""Verify Stage 1: Python environment is ready."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")

in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
print(f"Virtualenv: {'yes' if in_venv else 'no'} ({sys.prefix})")

if ENV_FILE.exists():
    print(".env: present (values not printed)")
else:
    print(".env: missing — copy .env.example to .env and fill in values")
    sys.exit(1)

if not in_venv:
    print("Not running inside .venv")
    sys.exit(1)

print("Stage 1 environment OK")
