"""Pydantic schemas for structured agent outputs."""

from typing import Optional
from pydantic import BaseModel, Field


class RepositoryAnalysis(BaseModel):
    """Machine-consumable repository analysis output schema."""

    language: str = Field(
        description="Primary programming language (e.g. Python, TypeScript, Go)"
    )
    framework: Optional[str] = Field(
        default=None,
        description="Core framework used (e.g. LangGraph / LangChain, Next.js, FastAPI)",
    )
    package_manager: Optional[str] = Field(
        default=None,
        description="Package or dependency manager used (e.g. pip, npm, poetry, cargo)",
    )
    entry_points: list[str] = Field(
        default_factory=list,
        description="Application or script entry point files (e.g. src/main.py, scripts/mcp_agent.py)",
    )
    build_command: Optional[str] = Field(
        default=None,
        description="Command used to install dependencies or build the project (e.g. pip install -r requirements.txt)",
    )
    test_command: Optional[str] = Field(
        default=None,
        description="Command used to run tests (e.g. pytest, npm test, or None if no tests exist)",
    )
    deployment_files: list[str] = Field(
        default_factory=list,
        description="Deployment, Docker, or CI/CD configuration files (e.g. Dockerfile, .github/workflows/ci.yml)",
    )
