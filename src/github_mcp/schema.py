"""MCP JSON Schema to Pydantic model conversion."""

from typing import Any, Optional
from pydantic import BaseModel, Field, create_model


def json_schema_to_python_type(field_schema: dict) -> Any:
    """Best-effort conversion of a JSON Schema field descriptor to a Python type.

    Handles string, integer, number, boolean, array, object, and anyOf/oneOf.
    """
    for combiner in ("anyOf", "oneOf"):
        if combiner in field_schema:
            for variant in field_schema[combiner]:
                if variant.get("type") != "null":
                    return Optional[json_schema_to_python_type(variant)]
            return Optional[Any]

    t = field_schema.get("type", "string")
    if t == "string":
        return str
    if t == "integer":
        return int
    if t == "number":
        return float
    if t == "boolean":
        return bool
    if t == "array":
        return list
    if t == "object":
        return dict
    return Any


def json_schema_to_pydantic_model(tool_name: str, json_schema: dict) -> type[BaseModel]:
    """Build a Pydantic model with declared fields from an MCP tool's input schema.

    LangChain inspects declared fields (not model_extra) when unpacking kwargs
    for _run / _arun, so every parameter the MCP server expects must be a real field.
    """
    props: dict = json_schema.get("properties") or {}
    required: set[str] = set(json_schema.get("required") or [])
    field_defs: dict[str, Any] = {}

    for field_name, field_schema in props.items():
        python_type = json_schema_to_python_type(field_schema)
        description = field_schema.get("description", "")
        if field_name in required:
            field_defs[field_name] = (python_type, Field(description=description))
        else:
            field_defs[field_name] = (
                Optional[python_type],
                Field(default=None, description=description),
            )

    return create_model(f"{tool_name}Input", **field_defs)
