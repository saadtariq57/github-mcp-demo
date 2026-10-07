"""Tool routing package."""

from src.router.catalog import build_catalog
from src.router.prompts import ROUTER_SYSTEM
from src.router.router import route_tools

__all__ = [
    "ROUTER_SYSTEM",
    "build_catalog",
    "route_tools",
]
