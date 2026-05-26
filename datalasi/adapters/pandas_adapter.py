"""Pandas DataFrame adapter for datalasi contract validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    import pandas as pd

    from datalasi.core.contract import DataContract, Field
    from datalasi.core.validation import ValidationResult


class PandasAdapter:
    """Validate a Pandas DataFrame against a :class:`~datalasi.core.contract.DataContract`."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def validate(df: "pd.DataFrame", contract: "DataContract") -> "ValidationResult":
        """Validate *df* against *contract* and return a
        :class:`~datalasi.core.validation.ValidationResult`.

        Checks performed, in order:
        1. Schema — missing columns, type mismatches, nullability violations,
           unknown columns, and Enum value violations.
        2. Expectations — each rule string is evaluated against *df*.
        3. Metadata — row count, null counts, cardinality.
        """
        import pandas as pd

        from datalasi.core.validation import (
            ExpectationViolation,
            SchemaViolation,
            ValidationResult,
        )

        result = ValidationResult(success=True)

        # ---- 1. Schema validation ----------------------------------------
        for col_name, field in contract.schema.items():
            if col_name not in df.columns:
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="MISSING_COLUMN",
                        column=col_name,
                        expected=field.type.name,
                    )
                )
                result.success = False
                continue

            series = df[col_name]

            # Type mismatch
            if not PandasAdapter._type_matches(series.dtype, field.type):
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="TYPE_MISMATCH",
                        column=col_name,
                        expected=field.type.name,
                        actual=str(series.dtype),
                    )
                )
                result.success = False

            # Nullability violation
            null_count = int(series.isnull().sum())
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

            # Enum value violations (values outside allowed set)
            from datalasi.core.types import Enum as EnumType

            if isinstance(field.type, EnumType):
                allowed = set(field.type.allowed_values)
                bad_mask = series.dropna().apply(lambda v: v not in allowed)
                bad_count = int(bad_mask.sum())
                if bad_count > 0:
                    bad_vals = series.dropna()[bad_mask].unique().tolist()[:10]
                    result.schema_violations.append(
                        SchemaViolation(
                            violation_type="TYPE_MISMATCH",
                            column=col_name,
                            expected=f"one of {field.type.allowed_values}",
                            actual=f"invalid values: {bad_vals}",
                            severity="ERROR",
                        )
                    )
                    result.success = False

        # Unknown columns (warning only — does not fail the result)
        for col in df.columns:
            if col not in contract.schema:
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="UNKNOWN_COLUMN",
                        column=col,
                        severity="WARNING",
                    )
                )

        # ---- 2. Expectations validation ----------------------------------
        for rule in contract.expectations:
            try:
                mask = PandasAdapter._eval_expectation(df, rule)
                failing = ~mask
                failing_count = int(failing.sum())
                if failing_count > 0:
                    failing_indices = df[failing].index.tolist()[:1000]
                    sample = []
                    for col in df.columns:
                        vals = df.loc[df[failing].index[:10], col].tolist()
                        if vals:
                            sample.extend(vals[:3])
                            break
                    result.expectation_violations.append(
                        ExpectationViolation(
                            rule=rule,
                            row_count=failing_count,
                            row_indices=failing_indices,
                            sample_values=sample,
                        )
                    )
                    result.success = False
            except Exception as exc:
                result.expectation_violations.append(
                    ExpectationViolation(
                        rule=rule,
                        description=f"Error evaluating rule: {exc}",
                        row_count=0,
                    )
                )
                result.success = False

        # ---- 3. Metadata -------------------------------------------------
        result.metadata = PandasAdapter._collect_metadata(df, contract)

        return result

    @staticmethod
    def infer_schema(df: "pd.DataFrame") -> Dict[str, "Field"]:
        """Infer a contract schema from a Pandas DataFrame.

        Maps each column's dtype to the closest contract type and detects
        whether the column contains nulls.

        Returns:
            A dict mapping column name → :class:`~datalasi.core.contract.Field`.
        """
        from datalasi.core.contract import Field
        from datalasi.core.types import Boolean, Date, Float64, Int32, Int64, String, Timestamp

        schema: Dict[str, Field] = {}
        for col in df.columns:
            series = df[col]
            dtype_str = str(series.dtype).lower()
            nullable = bool(series.isnull().any())

            if "int32" in dtype_str:
                col_type = Int32()
            elif "int" in dtype_str:
                col_type = Int64()
            elif "float" in dtype_str:
                col_type = Float64()
            elif "bool" in dtype_str:
                col_type = Boolean()
            elif "datetime" in dtype_str:
                col_type = Timestamp()
            elif "date" in dtype_str:
                col_type = Date()
            else:
                col_type = String()

            schema[col] = Field(name=col, type=col_type, nullable=nullable)

        return schema

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _type_matches(pandas_dtype: Any, contract_type: Any) -> bool:
        """Return True if *pandas_dtype* is compatible with *contract_type*.

        Handles both legacy pandas 'object' dtype and pandas 3.0+ 'str' dtype
        for string-like columns.
        """
        type_name = contract_type.name
        dtype_str = str(pandas_dtype).lower()

        # pandas 3.0+ uses 'str' dtype for string columns; older uses 'object'
        is_string_like = dtype_str in ("object", "string", "str") or "string" in dtype_str

        if type_name == "Int64":
            return "int" in dtype_str and "float" not in dtype_str
        if type_name == "Int32":
            return "int32" in dtype_str
        if type_name == "Float64":
            return "float" in dtype_str
        if type_name == "String":
            return is_string_like
        if type_name == "Boolean":
            return "bool" in dtype_str
        if type_name == "Timestamp":
            return "datetime" in dtype_str
        if type_name == "Date":
            return is_string_like or "date" in dtype_str
        if type_name == "Enum":
            return is_string_like or "category" in dtype_str
        return False

    @staticmethod
    def _eval_expectation(df: "pd.DataFrame", rule: str) -> "pd.Series":
        """Evaluate a rule string against *df* and return a boolean Series.

        Column names are available as variables in the expression.
        Example: ``"amount > 0"`` evaluates ``df['amount'] > 0``.
        """
        import pandas as pd

        namespace: Dict[str, Any] = {col: df[col] for col in df.columns}
        # Expose pandas for advanced rules: pd.notnull(x), etc.
        namespace["pd"] = pd
        namespace["len"] = len

        result = eval(rule, {"__builtins__": {}}, namespace)  # noqa: S307

        if isinstance(result, pd.Series):
            return result.astype(bool).fillna(False)
        # Scalar True/False — broadcast to all rows
        return pd.Series([bool(result)] * len(df), index=df.index)

    @staticmethod
    def _collect_metadata(df: "pd.DataFrame", contract: "DataContract") -> Dict[str, Any]:
        """Collect diagnostic metadata from *df*."""
        null_counts = df.isnull().sum().to_dict()
        null_pct = {
            col: round(count / len(df), 4) if len(df) > 0 else 0.0
            for col, count in null_counts.items()
        }

        # Cardinality for Enum and String columns (capped for performance)
        from datalasi.core.types import Enum as EnumType, String as StringType

        cardinality: Dict[str, int] = {}
        for col_name, field in contract.schema.items():
            if col_name in df.columns and isinstance(field.type, (EnumType, StringType)):
                cardinality[col_name] = int(df[col_name].nunique())

        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "null_counts": {k: int(v) for k, v in null_counts.items()},
            "null_pct": null_pct,
            "cardinality": cardinality,
        }
