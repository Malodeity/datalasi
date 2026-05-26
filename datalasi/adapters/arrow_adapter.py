"""PyArrow Table adapter for datalasi contract validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa

    from datalasi.core.contract import DataContract, Field
    from datalasi.core.validation import ValidationResult


class ArrowAdapter:
    """Validate a PyArrow :class:`~pyarrow.Table` against a
    :class:`~datalasi.core.contract.DataContract`.

    Requires the ``arrow`` optional dependency::

        pip install "datalasi[arrow]"
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def validate(table: pa.Table, contract: DataContract) -> ValidationResult:
        """Validate *table* against *contract*.

        Schema checks are performed natively on the Arrow schema.
        Expectations are evaluated by converting the table to a Pandas
        DataFrame and delegating to :class:`~datalasi.adapters.pandas_adapter.PandasAdapter`.
        """

        from datalasi.core.validation import (
            ExpectationViolation,
            SchemaViolation,
            ValidationResult,
        )

        result = ValidationResult(success=True)
        arrow_schema = table.schema

        # ---- 1. Schema validation ----------------------------------------
        for col_name, field in contract.schema.items():
            col_idx = arrow_schema.get_field_index(col_name)
            if col_idx == -1:
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="MISSING_COLUMN",
                        column=col_name,
                        expected=field.type.name,
                    )
                )
                result.success = False
                continue

            arrow_type = arrow_schema.field(col_name).type

            # Type mismatch
            if not ArrowAdapter._type_matches(arrow_type, field.type):
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="TYPE_MISMATCH",
                        column=col_name,
                        expected=field.type.name,
                        actual=str(arrow_type),
                    )
                )
                result.success = False

            # Nullability
            col = table.column(col_name)
            null_count = col.null_count
            if null_count > 0 and not field.nullable:
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="NULLABILITY_VIOLATION",
                        column=col_name,
                        expected="non-null",
                        actual=f"{null_count} null value(s)",
                    )
                )
                result.success = False

            # Enum value violations
            from datalasi.core.types import Enum as EnumType

            if isinstance(field.type, EnumType):
                allowed = set(field.type.allowed_values)
                flat = col.combine_chunks() if hasattr(col, "combine_chunks") else col
                bad = [v.as_py() for v in flat if v.is_valid and v.as_py() not in allowed]
                if bad:
                    result.schema_violations.append(
                        SchemaViolation(
                            violation_type="TYPE_MISMATCH",
                            column=col_name,
                            expected=f"one of {field.type.allowed_values}",
                            actual=f"invalid values: {bad[:10]}",
                            severity="ERROR",
                        )
                    )
                    result.success = False

        # Unknown columns
        for col_name in arrow_schema.names:
            if col_name not in contract.schema:
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="UNKNOWN_COLUMN",
                        column=col_name,
                        severity="WARNING",
                    )
                )

        # ---- 2. Expectations (delegate to pandas) -------------------------
        if contract.expectations:
            try:
                df = table.to_pandas()
                from datalasi.adapters.pandas_adapter import PandasAdapter

                for rule in contract.expectations:
                    if hasattr(rule, "to_expression"):
                        expr = rule.to_expression()
                        rule_label = str(rule)
                        severity = getattr(rule, "severity", "ERROR")
                    else:
                        expr = str(rule)
                        rule_label = expr
                        severity = "ERROR"

                    try:
                        mask = PandasAdapter._eval_expectation(df, expr)
                        failing_count = int((~mask).sum())
                        if failing_count > 0:
                            result.expectation_violations.append(
                                ExpectationViolation(
                                    rule=expr,
                                    description=rule_label if rule_label != expr else None,
                                    row_count=failing_count,
                                    row_indices=df[~mask].index.tolist()[:1000],
                                )
                            )
                            if severity == "ERROR":
                                result.success = False
                    except Exception as exc:
                        result.expectation_violations.append(
                            ExpectationViolation(
                                rule=expr,
                                description=f"Error evaluating rule: {exc}",
                                row_count=0,
                            )
                        )
                        result.success = False
            except ImportError:
                pass  # pandas not installed — skip expectation evaluation

        # ---- 3. Metadata -------------------------------------------------
        result.metadata = {
            "row_count": table.num_rows,
            "column_count": table.num_columns,
            "null_counts": {name: table.column(name).null_count for name in arrow_schema.names},
        }

        return result

    @staticmethod
    def infer_schema(table: pa.Table) -> dict[str, Field]:
        """Infer a contract schema from a PyArrow Table.

        Returns:
            A dict mapping column name → :class:`~datalasi.core.contract.Field`.
        """
        import pyarrow as pa

        from datalasi.core.contract import Field
        from datalasi.core.types import Boolean, Date, Float64, Int32, Int64, String, Timestamp

        schema: dict[str, Field] = {}
        for col_name in table.schema.names:
            arrow_type = table.schema.field(col_name).type
            col = table.column(col_name)
            nullable = col.null_count > 0

            if pa.types.is_int32(arrow_type):
                col_type = Int32()
            elif pa.types.is_integer(arrow_type):
                col_type = Int64()
            elif pa.types.is_floating(arrow_type):
                col_type = Float64()
            elif pa.types.is_boolean(arrow_type):
                col_type = Boolean()
            elif pa.types.is_date(arrow_type):
                col_type = Date()
            elif pa.types.is_timestamp(arrow_type):
                tz = getattr(arrow_type, "tz", None)
                col_type = Timestamp(timezone=tz)
            else:
                col_type = String()

            schema[col_name] = Field(name=col_name, type=col_type, nullable=nullable)

        return schema

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _type_matches(arrow_type: Any, contract_type: Any) -> bool:
        """Return True if *arrow_type* is compatible with *contract_type*.

        ``pa.null()`` (all-null columns) is accepted for any type — the type
        is unknowable, so we defer to the nullability check at the Field level.
        """
        import pyarrow as pa

        if pa.types.is_null(arrow_type):
            return True

        type_name = contract_type.name

        if type_name == "Int32":
            return pa.types.is_int32(arrow_type)
        if type_name == "Int64":
            return pa.types.is_integer(arrow_type)
        if type_name == "Float64":
            return pa.types.is_floating(arrow_type)
        if type_name == "String":
            return pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type)
        if type_name == "Boolean":
            return pa.types.is_boolean(arrow_type)
        if type_name == "Date":
            return pa.types.is_date(arrow_type)
        if type_name == "Timestamp":
            return pa.types.is_timestamp(arrow_type)
        if type_name == "Enum":
            return (
                pa.types.is_string(arrow_type)
                or pa.types.is_large_string(arrow_type)
                or pa.types.is_dictionary(arrow_type)
            )
        return False
