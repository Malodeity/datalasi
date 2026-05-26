"""Pandas DataFrame adapter for datalasi contract validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    def validate(
        df: pd.DataFrame, contract: DataContract, coerce: bool = False
    ) -> ValidationResult:
        """Validate *df* against *contract* and return a
        :class:`~datalasi.core.validation.ValidationResult`.

        Checks performed, in order:
        1. (Optional) Coercion — cast columns to their declared types when
           ``coerce=True``.  The original DataFrame is never mutated.
        2. Schema — missing columns, type mismatches, nullability violations,
           unknown columns, and Enum value violations.
        3. Expectations — each rule string or :class:`~datalasi.core.expectations.ExpectationRule`
           is evaluated against *df*.
        4. Metadata — row count, null counts, cardinality.

        Args:
            df: The DataFrame to validate.
            contract: The contract to validate against.
            coerce: When ``True``, attempt to coerce each column to its
                declared type before running schema checks.
        """

        from datalasi.core.validation import (
            ExpectationViolation,
            SchemaViolation,
            ValidationResult,
        )

        result = ValidationResult(success=True)

        # ---- 0. Coercion (optional) --------------------------------------
        if coerce:
            df = df.copy()
            for col_name, field in contract.schema.items():
                if col_name not in df.columns:
                    continue
                coerced, label = PandasAdapter._try_coerce_column(df[col_name], field.type)
                if label:
                    df[col_name] = coerced
                    result.coercions_applied.append(f"{col_name}: {label}")

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
                            rule=expr,
                            description=rule_label if rule_label != expr else None,
                            row_count=failing_count,
                            row_indices=failing_indices,
                            sample_values=sample,
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

        # ---- 3. Metadata -------------------------------------------------
        result.metadata = PandasAdapter._collect_metadata(df, contract)

        return result

    @staticmethod
    def infer_schema(df: pd.DataFrame) -> dict[str, Field]:
        """Infer a contract schema from a Pandas DataFrame.

        Maps each column's dtype to the closest contract type and detects
        whether the column contains nulls.

        Returns:
            A dict mapping column name → :class:`~datalasi.core.contract.Field`.
        """
        from datalasi.core.contract import Field
        from datalasi.core.types import Boolean, Date, Float64, Int32, Int64, String, Timestamp

        schema: dict[str, Field] = {}
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
    def _eval_expectation(df: pd.DataFrame, rule: str) -> pd.Series:
        """Evaluate a rule string against *df* and return a boolean Series.

        Column names are available as variables in the expression.
        Example: ``"amount > 0"`` evaluates ``df['amount'] > 0``.
        """
        import pandas as pd

        namespace: dict[str, Any] = {col: df[col] for col in df.columns}
        # Expose pandas for advanced rules: pd.notnull(x), etc.
        namespace["pd"] = pd
        namespace["len"] = len

        result = eval(rule, {"__builtins__": {}}, namespace)  # noqa: S307

        if isinstance(result, pd.Series):
            return result.astype(bool).fillna(False)
        # Scalar True/False — broadcast to all rows
        return pd.Series([bool(result)] * len(df), index=df.index)

    @staticmethod
    def _try_coerce_column(series: pd.Series, contract_type: Any) -> tuple[pd.Series, str]:
        """Attempt to cast *series* to *contract_type*.

        Returns:
            ``(coerced_series, label)`` where *label* describes the coercion
            (e.g. ``"object → Int64"``).  If no coercion is needed or possible,
            *label* is an empty string and *coerced_series* is the original.
        """
        import pandas as pd

        type_name = contract_type.name
        orig_dtype = str(series.dtype)

        try:
            if type_name in ("Int64", "Int32"):
                target = "Int64" if type_name == "Int64" else "Int32"
                coerced = pd.to_numeric(series, errors="coerce").astype(target)
            elif type_name == "Float64":
                coerced = pd.to_numeric(series, errors="coerce")
            elif type_name in ("String", "Enum", "Date"):
                coerced = series.where(series.isna(), series.astype(str))
            elif type_name == "Boolean":
                coerced = series.astype(bool)
            else:
                return series, ""

            if str(coerced.dtype) != orig_dtype:
                return coerced, f"{orig_dtype} → {type_name}"
            return series, ""
        except Exception:
            return series, ""

    @staticmethod
    def _collect_metadata(df: pd.DataFrame, contract: DataContract) -> dict[str, Any]:
        """Collect diagnostic metadata from *df*."""
        null_counts = df.isnull().sum().to_dict()
        null_pct = {
            col: round(count / len(df), 4) if len(df) > 0 else 0.0
            for col, count in null_counts.items()
        }

        # Cardinality for Enum and String columns (capped for performance)
        from datalasi.core.types import Enum as EnumType
        from datalasi.core.types import String as StringType

        cardinality: dict[str, int] = {}
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
