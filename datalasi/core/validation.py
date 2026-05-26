"""Result types returned by contract validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class SchemaViolation:
    """A single schema-level violation found during validation.

    Attributes:
        violation_type: One of MISSING_COLUMN, TYPE_MISMATCH,
            UNKNOWN_COLUMN, NULLABILITY_VIOLATION.
        column: The column name where the violation occurred.
        expected: What the contract expected (type name, constraint, etc.).
        actual: What was actually found in the data.
        severity: ERROR (contract broken) or WARNING (advisory only).
    """

    violation_type: Literal[
        "MISSING_COLUMN", "TYPE_MISMATCH", "UNKNOWN_COLUMN", "NULLABILITY_VIOLATION"
    ]
    column: str
    expected: Any | None = None
    actual: Any | None = None
    severity: Literal["ERROR", "WARNING"] = "ERROR"

    def __str__(self) -> str:
        parts = [f"[{self.severity}] {self.violation_type} on column '{self.column}'"]
        if self.expected is not None:
            parts.append(f"expected={self.expected!r}")
        if self.actual is not None:
            parts.append(f"actual={self.actual!r}")
        return " — ".join(parts)


@dataclass
class ExpectationViolation:
    """Records rows that failed a data-quality expectation rule.

    Attributes:
        rule: The expectation string that was evaluated (e.g. ``"amount > 0"``).
        description: Optional human-readable description of the rule.
        row_count: Number of rows that violated the rule.
        row_indices: List of row indices (0-based) that violated the rule.
        sample_values: Up to 10 sample failing values for diagnostics.
    """

    rule: str
    description: str | None = None
    row_count: int = 0
    row_indices: list[int] = field(default_factory=list)
    sample_values: list[Any] = field(default_factory=list)

    def __str__(self) -> str:
        label = self.description or self.rule
        return f"ExpectationViolation: {label!r} failed on {self.row_count} row(s)"


@dataclass
class ValidationResult:
    """The outcome of validating data against a :class:`DataContract`.

    Attributes:
        success: True only when there are no schema violations *and* no
            expectation violations.
        schema_violations: List of schema-level issues found.
        expectation_violations: List of data-quality rule failures.
        breaking_changes_detected: Breaking change descriptions detected when
            comparing contract versions (populated by the adapter layer).
        coercions_applied: List of columns that were coerced to their declared
            types when ``coerce=True`` was passed to the adapter.
        metadata: Diagnostic metadata — row counts, null percentages, etc.
    """

    success: bool
    schema_violations: list[SchemaViolation] = field(default_factory=list)
    expectation_violations: list[ExpectationViolation] = field(default_factory=list)
    breaking_changes_detected: list[str] = field(default_factory=list)
    coercions_applied: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.success else "FAIL"
        lines = [f"ValidationResult({status})"]
        if self.schema_violations:
            lines.append(f"  schema_violations ({len(self.schema_violations)}):")
            for v in self.schema_violations:
                lines.append(f"    {v}")
        if self.expectation_violations:
            lines.append(f"  expectation_violations ({len(self.expectation_violations)}):")
            for v in self.expectation_violations:
                lines.append(f"    {v}")
        if self.coercions_applied:
            lines.append(f"  coercions_applied ({len(self.coercions_applied)}):")
            for c in self.coercions_applied:
                lines.append(f"    {c}")
        return "\n".join(lines)
