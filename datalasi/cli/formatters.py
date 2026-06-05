"""Rich-powered terminal formatters for datalasi CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from datalasi.core.validation import ValidationResult
    from datalasi.io.registry import ContractDiff

console = Console()


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


def print_validation_result(result: ValidationResult, contract_name: str = "") -> None:
    """Render a :class:`~datalasi.core.validation.ValidationResult` to the terminal."""
    row_count = result.metadata.get("row_count", "?")
    col_count = result.metadata.get("column_count", "?")

    rows_str = f"{row_count:,}" if isinstance(row_count, int) else str(row_count)
    meta_str = f"{rows_str} rows · {col_count} columns"

    if result.success:
        title = Text()
        title.append(" ✓  PASS  ", style="bold green")
        title.append(contract_name, style="bold")
        body_lines: list[Any] = [Text(meta_str, style="dim")]
        if result.coercions_applied:
            body_lines.append(
                Text(f"Coercions: {', '.join(result.coercions_applied)}", style="dim")
            )
        console.print(Panel(Group(*body_lines), title=title, border_style="green", padding=(0, 2)))
        return

    # ---- FAIL ----
    title = Text()
    title.append(" ✗  FAIL  ", style="bold red")
    title.append(contract_name, style="bold")

    body: list[Any] = [Text(meta_str, style="dim")]

    if result.schema_violations:
        body.append(Text(""))
        body.append(
            Text(f"Schema Violations ({len(result.schema_violations)})", style="bold yellow")
        )
        body.append(_schema_violation_table(result.schema_violations))

    if result.expectation_violations:
        body.append(Text(""))
        body.append(
            Text(
                f"Expectation Violations ({len(result.expectation_violations)})",
                style="bold yellow",
            )
        )
        body.append(_expectation_violation_table(result.expectation_violations))

    if result.coercions_applied:
        body.append(Text(f"Coercions: {', '.join(result.coercions_applied)}", style="dim"))

    console.print(Panel(Group(*body), title=title, border_style="red", padding=(0, 2)))


def _schema_violation_table(violations: list[Any]) -> Table:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("Type", style="bold", no_wrap=True)
    table.add_column("Column", style="cyan")
    table.add_column("Details")

    for v in violations:
        style = "red" if v.severity == "ERROR" else "yellow"
        vtype = Text(v.violation_type, style=style)
        details_parts = []
        if v.expected is not None:
            details_parts.append(f"expected: {v.expected}")
        if v.actual is not None:
            details_parts.append(f"got: {v.actual}")
        table.add_row(vtype, v.column, "  ".join(details_parts))

    return table


def _expectation_violation_table(violations: list[Any]) -> Table:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", padding=(0, 1))
    table.add_column("Rule", style="cyan", max_width=45)
    table.add_column("Rows", justify="right", style="bold red")
    table.add_column("Sample values", style="dim")

    for v in violations:
        label = v.description or v.rule
        sample = ", ".join(str(x) for x in v.sample_values[:5]) if v.sample_values else "—"
        table.add_row(label, str(v.row_count), sample)

    return table


# ---------------------------------------------------------------------------
# Diff output
# ---------------------------------------------------------------------------


def print_diff(diff: ContractDiff) -> None:
    """Render a :class:`~datalasi.io.registry.ContractDiff` to the terminal."""
    has_changes = bool(diff.breaking_changes or diff.non_breaking_changes)
    has_breaking = diff.has_breaking_changes

    header = Text()
    header.append(diff.name, style="bold")
    header.append("  ")
    header.append(diff.v1, style="dim")
    header.append(" → ", style="dim")
    header.append(diff.v2, style="dim")

    if not has_changes:
        console.print(
            Panel(
                Group(header, Text("No schema changes detected.", style="dim green")),
                border_style="green",
                padding=(0, 2),
            )
        )
        return

    parts: list[str] = []
    if diff.breaking_changes:
        parts.append(f"[bold red]{len(diff.breaking_changes)} breaking[/bold red]")
    if diff.non_breaking_changes:
        parts.append(f"[green]{len(diff.non_breaking_changes)} non-breaking[/green]")
    summary = Text.from_markup(" · ".join(parts))

    lines: list[Any] = [header, summary]

    if diff.breaking_changes:
        lines.append(Text(""))
        lines.append(Text("Breaking Changes", style="bold red"))
        for change in diff.breaking_changes:
            t = Text()
            t.append("  ✗  ", style="red")
            t.append(change)
            lines.append(t)

    if diff.non_breaking_changes:
        lines.append(Text(""))
        lines.append(Text("Non-breaking Changes", style="bold green"))
        for change in diff.non_breaking_changes:
            t = Text()
            t.append("  +  ", style="green")
            t.append(change)
            lines.append(t)

    console.print(
        Panel(
            Group(*lines),
            border_style="red" if has_breaking else "green",
            padding=(0, 2),
        )
    )


# ---------------------------------------------------------------------------
# Registry listing
# ---------------------------------------------------------------------------


def print_registry(contracts: dict[str, list[str]]) -> None:
    """Render a contract registry summary table."""
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
        padding=(0, 2),
    )
    table.add_column("Contract", style="bold cyan")
    table.add_column("Versions", style="dim")
    table.add_column("Latest", style="bold green")

    for name in sorted(contracts):
        versions = contracts[name]
        older = "  ".join(versions[:-1]) if len(versions) > 1 else ""
        latest = versions[-1] if versions else "—"
        table.add_row(name, older, latest)

    console.print(table)
