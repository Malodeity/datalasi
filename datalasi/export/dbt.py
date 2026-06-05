"""dbt schema.yml export for datalasi DataContracts.

Converts a contract into a ready-to-use dbt schema file with standard tests
inferred from the contract's field definitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract, Field


def to_dbt_schema(
    contract: DataContract,
    model_name: str | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    """Convert a :class:`~datalasi.core.contract.DataContract` to a dbt schema structure.

    The returned dict is YAML-serialisable and can be written directly to a
    ``schema.yml`` (or ``models/staging/_sources.yml``) file.

    **Tests generated automatically:**

    ==================  =====================================================
    Contract metadata   dbt test
    ==================  =====================================================
    ``nullable=False``  ``not_null``
    ``pk=True``         ``unique``
    ``Enum`` type       ``accepted_values``
    numeric ``min``     ``dbt_utils.expression_is_true`` (requires dbt-utils)
    numeric ``max``     ``dbt_utils.expression_is_true``
    string ``max_length`` ``dbt_utils.expression_is_true``
    ==================  =====================================================

    Args:
        contract: The contract to export.
        model_name: Override the model / table name (defaults to
            ``contract.name``).
        source_name: When set, wraps the entry in a ``sources`` block instead
            of a ``models`` block — useful for staging layer contracts.

    Returns:
        A dict representing the dbt ``schema.yml`` structure.

    Example::

        schema = to_dbt_schema(contract)
        with open("models/staging/schema.yml", "w") as f:
            yaml.dump(schema, f, sort_keys=False)
    """
    name = model_name or contract.name
    columns = [_column_entry(col_name, field) for col_name, field in contract.schema.items()]

    entry: dict[str, Any] = {"name": name}
    if contract.description:
        entry["description"] = contract.description

    entry["meta"] = {"contract_version": contract.version}
    if contract.owner:
        entry["meta"]["contract_owner"] = contract.owner

    entry["columns"] = columns

    if source_name:
        return {
            "version": 2,
            "sources": [{"name": source_name, "tables": [entry]}],
        }

    return {"version": 2, "models": [entry]}


def to_dbt_schema_yaml(
    contract: DataContract,
    model_name: str | None = None,
    source_name: str | None = None,
) -> str:
    """Return the dbt schema as a YAML string (convenience wrapper)."""
    import yaml

    return yaml.dump(
        to_dbt_schema(contract, model_name=model_name, source_name=source_name),
        default_flow_style=False,
        sort_keys=False,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _column_entry(col_name: str, field: Field) -> dict[str, Any]:
    """Build a single dbt column entry dict."""
    tests = _build_tests(field)
    entry: dict[str, Any] = {"name": col_name}
    if field.description:
        entry["description"] = field.description
    if tests:
        entry["tests"] = tests
    return entry


def _build_tests(field: Field) -> list[Any]:
    """Return the list of dbt test definitions for *field*."""
    from datalasi.core.types import Enum as EnumType

    tests: list[Any] = []

    if not field.nullable:
        tests.append("not_null")

    if field.pk:
        tests.append("unique")

    if isinstance(field.type, EnumType):
        tests.append({"accepted_values": {"values": list(field.type.allowed_values)}})

    min_val = getattr(field.type, "min", None)
    max_val = getattr(field.type, "max", None)
    max_length = getattr(field.type, "max_length", None)

    if min_val is not None:
        tests.append({"dbt_utils.expression_is_true": {"expression": f"{field.name} >= {min_val}"}})
    if max_val is not None:
        tests.append({"dbt_utils.expression_is_true": {"expression": f"{field.name} <= {max_val}"}})
    if max_length is not None:
        tests.append(
            {
                "dbt_utils.expression_is_true": {
                    "expression": f"length({field.name}) <= {max_length}"
                }
            }
        )

    return tests
