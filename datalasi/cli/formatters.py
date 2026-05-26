"""Pretty-print helpers for the datalasi CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from datalasi.core.validation import ValidationResult
    from datalasi.io.registry import ContractDiff


def print_validation_result(result: ValidationResult, contract_name: str) -> None:
    """Print a human-readable validation summary to stdout."""
    row_count = result.metadata.get("row_count", "?")
    col_count = result.metadata.get("column_count", "?")

    if result.success:
        click.echo(
            click.style("✓ PASS", fg="green", bold=True)
            + f"  {contract_name}"
            + f"  |  {row_count:,} rows  |  {col_count} columns"
        )
        return

    click.echo(
        click.style("✗ FAIL", fg="red", bold=True)
        + f"  {contract_name}"
        + f"  |  {row_count:,} rows  |  {col_count} columns"
    )

    if result.schema_violations:
        click.echo(f"\n  Schema violations ({len(result.schema_violations)}):")
        for v in result.schema_violations:
            color = "red" if v.severity == "ERROR" else "yellow"
            prefix = "  ✗" if v.severity == "ERROR" else "  ⚠"
            msg = f"{prefix} [{v.violation_type}] column '{v.column}'"
            if v.expected is not None:
                msg += f"  expected={v.expected!r}"
            if v.actual is not None:
                msg += f"  actual={v.actual!r}"
            click.echo(click.style(msg, fg=color))

    if result.expectation_violations:
        click.echo(f"\n  Expectation violations ({len(result.expectation_violations)}):")
        for v in result.expectation_violations:
            msg = f"  ✗ {v.rule!r}"
            if v.row_count:
                msg += f"  failed on {v.row_count:,} row(s)"
            if v.description:
                msg += f"  — {v.description}"
            click.echo(click.style(msg, fg="red"))


def print_diff(diff: ContractDiff) -> None:
    """Print a human-readable diff summary to stdout."""
    click.echo(f"\n{diff.name}: {diff.v1} → {diff.v2}")

    if not diff.breaking_changes and not diff.non_breaking_changes:
        click.echo(click.style("  No schema changes detected.", fg="green"))
        return

    if diff.breaking_changes:
        click.echo(
            click.style(
                f"\n  Breaking changes ({len(diff.breaking_changes)}):", fg="red", bold=True
            )
        )
        for c in diff.breaking_changes:
            click.echo(click.style(f"    ✗ {c}", fg="red"))

    if diff.non_breaking_changes:
        click.echo(
            click.style(f"\n  Non-breaking changes ({len(diff.non_breaking_changes)}):", fg="green")
        )
        for c in diff.non_breaking_changes:
            click.echo(click.style(f"    + {c}", fg="green"))


def print_registry(contracts: dict) -> None:
    """Print a formatted contract registry listing."""
    if not contracts:
        click.echo("No contracts found.")
        return

    click.echo(f"\nFound {len(contracts)} contract(s):\n")
    for name in sorted(contracts):
        versions = contracts[name]
        latest = versions[-1] if versions else "?"
        version_list = ", ".join(versions)
        click.echo(
            f"  {click.style(name, bold=True)}  "
            f"[{version_list}]  " + click.style(f"(latest: {latest})", fg="cyan")
        )
