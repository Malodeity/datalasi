"""Structured expectation DSL for datalasi data contracts.

Rules can be expressed as plain Python strings (``"amount > 0"``) or as
structured :class:`ExpectationRule` objects that serialise to YAML,
auto-generate human-readable descriptions, and produce both pandas
and Polars native expressions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ExpectationRule:
    """A structured data-quality rule applied to a single column.

    Attributes:
        column: Column name this rule applies to.
        rule: Rule type — one of the supported rule names.
        value: Threshold / reference value.  Not required for ``not_null``
            and ``unique``.  For ``in`` / ``not_in`` pass a list.
            For ``between`` pass ``[low, high]``.
        description: Optional label used in violation reports.
        severity: ``"ERROR"`` causes validation to fail; ``"WARNING"`` records
            the violation without failing.
    """

    column: str
    rule: Literal[
        "not_null",
        "unique",
        "gt",
        "gte",
        "lt",
        "lte",
        "eq",
        "ne",
        "in",
        "not_in",
        "regex",
        "between",
    ]
    value: Any = None
    description: str | None = None
    severity: Literal["ERROR", "WARNING"] = "ERROR"

    def to_expression(self) -> str:
        """Return a pandas-compatible eval expression string for this rule.

        The returned string uses column names as variables — matching the
        namespace injected by :meth:`~datalasi.adapters.pandas_adapter.PandasAdapter._eval_expectation`.
        """
        col = self.column
        val = repr(self.value)

        if self.rule == "not_null":
            return f"~{col}.isnull()"
        if self.rule == "unique":
            return f"~{col}.duplicated(keep=False)"
        if self.rule == "gt":
            return f"{col} > {val}"
        if self.rule == "gte":
            return f"{col} >= {val}"
        if self.rule == "lt":
            return f"{col} < {val}"
        if self.rule == "lte":
            return f"{col} <= {val}"
        if self.rule == "eq":
            return f"{col} == {val}"
        if self.rule == "ne":
            return f"{col} != {val}"
        if self.rule == "in":
            return f"{col}.isin({val})"
        if self.rule == "not_in":
            return f"~{col}.isin({val})"
        if self.rule == "regex":
            return f"{col}.str.match({val}, na=False)"
        if self.rule == "between":
            lo, hi = self.value
            return f"({col} >= {lo!r}) & ({col} <= {hi!r})"
        raise ValueError(f"Unknown rule type: {self.rule!r}")

    def to_polars_expr(self) -> Any:
        """Return a Polars expression (``pl.Expr``) equivalent of this rule.

        Returns a boolean Series expression for use in
        ``df.select(rule.to_polars_expr())``.
        """
        import polars as pl

        col = pl.col(self.column)
        val = self.value

        if self.rule == "not_null":
            return col.is_not_null()
        if self.rule == "unique":
            return col.is_duplicated().not_()
        if self.rule == "gt":
            return col > val
        if self.rule == "gte":
            return col >= val
        if self.rule == "lt":
            return col < val
        if self.rule == "lte":
            return col <= val
        if self.rule == "eq":
            return col == val
        if self.rule == "ne":
            return col != val
        if self.rule == "in":
            return col.is_in(val)
        if self.rule == "not_in":
            return col.is_in(val).not_()
        if self.rule == "regex":
            return col.str.contains(val)
        if self.rule == "between":
            lo, hi = val
            return (col >= lo) & (col <= hi)
        raise ValueError(f"Unknown rule type: {self.rule!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for YAML storage."""
        d: dict[str, Any] = {"column": self.column, "rule": self.rule}
        if self.value is not None:
            d["value"] = self.value
        if self.description is not None:
            d["description"] = self.description
        if self.severity != "ERROR":
            d["severity"] = self.severity
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExpectationRule:
        """Deserialise from a plain dict (e.g. loaded from YAML)."""
        return cls(
            column=d["column"],
            rule=d["rule"],
            value=d.get("value"),
            description=d.get("description"),
            severity=d.get("severity", "ERROR"),
        )

    def __str__(self) -> str:
        if self.description:
            return self.description
        label = f"{self.column} {self.rule}"
        if self.value is not None:
            label += f" {self.value}"
        return label
