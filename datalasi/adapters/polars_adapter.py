"""Polars DataFrame adapter for datalasi contract validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

    from datalasi.core.contract import DataContract, Field
    from datalasi.core.validation import ValidationResult


class PolarsAdapter:
    """Validate a Polars DataFrame against a :class:`~datalasi.core.contract.DataContract`."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def validate(
        df: pl.DataFrame, contract: DataContract, coerce: bool = False
    ) -> ValidationResult:
        """Validate *df* against *contract* and return a
        :class:`~datalasi.core.validation.ValidationResult`.

        Checks performed, in order:
        1. (Optional) Coercion — cast columns to their declared types when
           ``coerce=True``.
        2. Schema — missing columns, type mismatches, nullability violations,
           unknown columns, and Enum value violations.
        3. Expectations — each rule string or
           :class:`~datalasi.core.expectations.ExpectationRule` is evaluated.
        4. Metadata — row count, null counts, cardinality.

        Args:
            df: The Polars DataFrame to validate.
            contract: The contract to validate against.
            coerce: When ``True``, attempt to cast each column to its declared type.
        """
        from datalasi.core.validation import (
            ExpectationViolation,
            SchemaViolation,
            ValidationResult,
        )

        result = ValidationResult(success=True)

        # ---- 0. Coercion (optional) --------------------------------------
        if coerce:
            for col_name, field in contract.schema.items():
                if col_name not in df.columns:
                    continue
                coerced_df, label = PolarsAdapter._try_coerce_column(df, col_name, field.type)
                if label:
                    df = coerced_df
                    result.coercions_applied.append(f"{col_name}: {label}")

        # ---- 1. Schema validation ----------------------------------------
        schema_types = dict(zip(df.columns, df.dtypes))

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

            polars_dtype = schema_types[col_name]
            series = df[col_name]

            # Type mismatch
            if not PolarsAdapter._type_matches(polars_dtype, field.type):
                result.schema_violations.append(
                    SchemaViolation(
                        violation_type="TYPE_MISMATCH",
                        column=col_name,
                        expected=field.type.name,
                        actual=str(polars_dtype),
                    )
                )
                result.success = False

            # Nullability violation
            null_count = series.null_count()
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

                non_null = series.drop_nulls()
                if len(non_null) > 0:
                    bad_series = non_null.filter(~non_null.is_in(field.type.allowed_values))
                    bad_count = len(bad_series)
                    if bad_count > 0:
                        bad_vals = bad_series.head(10).to_list()
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

        # Unknown columns (warning only)
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
                mask = PolarsAdapter._eval_expectation(df, expr)
                failing_indices = [i for i, v in enumerate(mask.to_list()) if not v]
                failing_count = len(failing_indices)
                if failing_count > 0:
                    result.expectation_violations.append(
                        ExpectationViolation(
                            rule=expr,
                            description=rule_label if rule_label != expr else None,
                            row_count=failing_count,
                            row_indices=failing_indices[:1000],
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
        result.metadata = PolarsAdapter._collect_metadata(df, contract)

        return result

    @staticmethod
    def infer_schema(df: pl.DataFrame) -> dict[str, Field]:
        """Infer a contract schema from a Polars DataFrame.

        Returns:
            A dict mapping column name → :class:`~datalasi.core.contract.Field`.
        """
        import polars as pl

        from datalasi.core.contract import Field
        from datalasi.core.types import Boolean, Date, Float64, Int32, Int64, String, Timestamp

        schema: dict[str, Field] = {}
        for col_name, dtype in zip(df.columns, df.dtypes):
            nullable = df[col_name].null_count() > 0

            if dtype == pl.Int32:
                col_type = Int32()
            elif dtype in (
                pl.Int8,
                pl.Int16,
                pl.Int64,
                pl.UInt8,
                pl.UInt16,
                pl.UInt32,
                pl.UInt64,
            ):
                col_type = Int64()
            elif dtype in (pl.Float32, pl.Float64):
                col_type = Float64()
            elif dtype == pl.Boolean:
                col_type = Boolean()
            elif dtype == pl.Date:
                col_type = Date()
            elif isinstance(dtype, pl.Datetime):
                tz = getattr(dtype, "time_zone", None)
                col_type = Timestamp(timezone=tz)
            elif dtype in PolarsAdapter._string_dtypes():
                col_type = String()
            else:
                col_type = String()

            schema[col_name] = Field(name=col_name, type=col_type, nullable=nullable)

        return schema

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _string_dtypes() -> tuple:
        """Return the set of Polars string/UTF-8 dtypes (handles API changes)."""
        import polars as pl

        dtypes = []
        for name in ("Utf8", "String"):
            dt = getattr(pl, name, None)
            if dt is not None:
                dtypes.append(dt)
        return tuple(dtypes)

    @staticmethod
    def _bool_dtype() -> Any:
        """Return the Polars Boolean dtype."""
        import polars as pl

        return pl.Boolean

    @staticmethod
    def _type_matches(polars_dtype: Any, contract_type: Any) -> bool:
        """Return True if *polars_dtype* is compatible with *contract_type*.

        A ``Null`` dtype column (all-null values) is accepted for any type —
        nullability is enforced separately at the Field level.
        """
        import polars as pl

        # Null dtype means the column is entirely null; the type is unknowable —
        # accept it here and let the nullability check catch non-nullable violations.
        if polars_dtype == pl.Null:
            return True

        type_name = contract_type.name
        dtype_str = str(polars_dtype).lower()

        if type_name == "Int64":
            return (
                polars_dtype
                in (
                    pl.Int8,
                    pl.Int16,
                    pl.Int64,
                    pl.UInt8,
                    pl.UInt16,
                    pl.UInt32,
                    pl.UInt64,
                )
                or "int" in dtype_str
            )
        if type_name == "Int32":
            return polars_dtype == pl.Int32 or dtype_str == "int32"
        if type_name == "Float64":
            return polars_dtype in (pl.Float32, pl.Float64) or "float" in dtype_str
        if type_name == "String":
            return polars_dtype in PolarsAdapter._string_dtypes() or "str" in dtype_str
        if type_name == "Boolean":
            return polars_dtype == pl.Boolean
        if type_name == "Timestamp":
            return isinstance(polars_dtype, pl.Datetime) or "datetime" in dtype_str
        if type_name == "Date":
            return polars_dtype == pl.Date or "date" in dtype_str
        if type_name == "Enum":
            return (
                polars_dtype in PolarsAdapter._string_dtypes()
                or isinstance(polars_dtype, pl.Categorical)
                or "str" in dtype_str
                or "categorical" in dtype_str
            )
        return False

    @staticmethod
    def _eval_expectation(df: pl.DataFrame, rule: str) -> pl.Series:
        """Evaluate a rule string and return a boolean Series.

        Column names are bound as variables (Polars Series) in the expression.
        Example: ``"amount > 0"`` → ``df['amount'] > 0``.
        """
        import polars as pl

        namespace: dict[str, Any] = {col: df[col] for col in df.columns}
        namespace["pl"] = pl
        namespace["len"] = len

        result = eval(rule, {"__builtins__": {}}, namespace)  # noqa: S307

        if isinstance(result, pl.Series):
            return result.cast(pl.Boolean).fill_null(False)
        # Scalar
        return pl.Series([bool(result)] * len(df))

    @staticmethod
    def _try_coerce_column(
        df: pl.DataFrame, col_name: str, contract_type: Any
    ) -> tuple[pl.DataFrame, str]:
        """Attempt to cast *col_name* in *df* to *contract_type*.

        Returns:
            ``(new_df, label)`` where *label* describes the coercion.
            Returns ``(df, "")`` if no coercion is needed or possible.
        """
        import polars as pl

        type_name = contract_type.name
        orig_dtype = str(df[col_name].dtype)

        dtype_map: dict[str, Any] = {
            "Int64": pl.Int64,
            "Int32": pl.Int32,
            "Float64": pl.Float64,
            "Boolean": pl.Boolean,
            "Date": pl.Date,
            "Timestamp": pl.Datetime,
        }

        if type_name in ("String", "Enum"):
            target = pl.Utf8
        elif type_name in dtype_map:
            target = dtype_map[type_name]
        else:
            return df, ""

        try:
            new_df = df.with_columns(pl.col(col_name).cast(target, strict=False))
            new_dtype = str(new_df[col_name].dtype)
            if new_dtype != orig_dtype:
                return new_df, f"{orig_dtype} → {type_name}"
            return df, ""
        except Exception:
            return df, ""

    @staticmethod
    def _collect_metadata(df: pl.DataFrame, contract: DataContract) -> dict[str, Any]:
        """Collect diagnostic metadata from *df*."""
        from datalasi.core.types import Enum as EnumType
        from datalasi.core.types import String as StringType

        null_counts = {col: df[col].null_count() for col in df.columns}
        null_pct = {
            col: round(count / len(df), 4) if len(df) > 0 else 0.0
            for col, count in null_counts.items()
        }

        cardinality: dict[str, int] = {}
        for col_name, field in contract.schema.items():
            if col_name in df.columns and isinstance(field.type, (EnumType, StringType)):
                cardinality[col_name] = df[col_name].n_unique()

        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "null_counts": null_counts,
            "null_pct": null_pct,
            "cardinality": cardinality,
        }
