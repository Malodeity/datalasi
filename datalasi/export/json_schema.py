"""JSON Schema (draft-07) export for datalasi DataContracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract, Field


def to_json_schema(contract: DataContract) -> dict[str, Any]:
    """Convert a :class:`~datalasi.core.contract.DataContract` to a JSON Schema document.

    The returned dict is JSON-serialisable and conforms to draft-07.

    Type mappings:

    ============  =======================================
    datalasi      JSON Schema
    ============  =======================================
    Int64 / Int32 ``{"type": "integer"}``
    Float64       ``{"type": "number"}``
    String        ``{"type": "string"}``
    Boolean       ``{"type": "boolean"}``
    Date          ``{"type": "string", "format": "date"}``
    Timestamp     ``{"type": "string", "format": "date-time"}``
    Enum          ``{"type": "string", "enum": [...]}``
    ============  =======================================

    Nullable fields use ``anyOf: [<type>, {"type": "null"}]``.
    Non-nullable fields appear in the top-level ``required`` list.
    Numeric and string constraints (``min``, ``max``, ``max_length``,
    ``pattern``) are mapped to their JSON Schema equivalents.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    for col_name, field in contract.schema.items():
        prop = _field_to_property(field)
        properties[col_name] = prop
        if not field.nullable:
            required.append(col_name)

    schema: dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": contract.name,
        "description": contract.description or f"Contract {contract.name} v{contract.version}",
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _field_to_property(field: Field) -> dict[str, Any]:
    from datalasi.core.types import (
        Boolean,
        Date,
        Enum,
        Float64,
        Int32,
        Int64,
        String,
        Timestamp,
    )

    t = field.type

    if isinstance(t, (Int64, Int32)):
        prop: dict[str, Any] = {"type": "integer"}
        if t.min is not None:
            prop["minimum"] = t.min
        if t.max is not None:
            prop["maximum"] = t.max
    elif isinstance(t, Float64):
        prop = {"type": "number"}
        if t.min is not None:
            prop["minimum"] = t.min
        if t.max is not None:
            prop["maximum"] = t.max
    elif isinstance(t, Boolean):
        prop = {"type": "boolean"}
    elif isinstance(t, Date):
        prop = {"type": "string", "format": "date"}
    elif isinstance(t, Timestamp):
        prop = {"type": "string", "format": "date-time"}
    elif isinstance(t, Enum):
        prop = {"type": "string", "enum": list(t.allowed_values)}
    elif isinstance(t, String):
        prop = {"type": "string"}
        if t.max_length is not None:
            prop["maxLength"] = t.max_length
        if t.pattern is not None:
            prop["pattern"] = t.pattern
    else:
        prop = {"type": "string"}

    if field.description:
        prop["description"] = field.description

    if field.nullable:
        return {"anyOf": [prop, {"type": "null"}]}

    return prop
