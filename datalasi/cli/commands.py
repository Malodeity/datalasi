"""datalasi CLI entry point.

Commands:
  validate  — validate a CSV/Parquet file against a contract
  infer     — infer a contract schema from a data file
  list      — list contracts in a registry directory
  diff      — show breaking/non-breaking changes between two contract versions
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from datalasi.version import __version__


@click.group()
@click.version_option(__version__, prog_name="datalasi")
def main() -> None:
    """datalasi — versioned data schema enforcement for Python."""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@main.command()
@click.argument("contract_path", metavar="CONTRACT")
@click.argument("data_path", metavar="DATA")
@click.option(
    "--fail-on-warning",
    is_flag=True,
    default=False,
    help="Exit with non-zero status even for WARNING-level schema violations.",
)
def validate(contract_path: str, data_path: str, fail_on_warning: bool) -> None:
    """Validate DATA against a CONTRACT.

    CONTRACT is a path to a YAML contract file.
    DATA is a path to a CSV or Parquet file.

    Exit code: 0 on success, 1 on validation failure, 2 on error.

    Example:

        datalasi validate contracts/transactions-v1.0.0.yaml data/tx.csv
    """
    from datalasi.cli.formatters import print_validation_result
    from datalasi.errors import ContractLoadError

    # Load contract
    try:
        from datalasi.io.loaders import YAMLLoader

        contract = YAMLLoader.load(contract_path)
    except FileNotFoundError:
        click.echo(
            click.style(f"Error: contract file not found: {contract_path}", fg="red"), err=True
        )
        sys.exit(2)
    except ContractLoadError as exc:
        click.echo(click.style(f"Error loading contract: {exc}", fg="red"), err=True)
        sys.exit(2)

    # Load data
    try:
        df = _load_data(data_path)
    except Exception as exc:
        click.echo(click.style(f"Error loading data: {exc}", fg="red"), err=True)
        sys.exit(2)

    # Run validation
    try:
        result = contract.validate(df)
    except ImportError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        click.echo("Install the required adapter: pip install 'datalasi[pandas]'", err=True)
        sys.exit(2)

    print_validation_result(result, contract.name)

    if not result.success:
        sys.exit(1)
    if fail_on_warning:
        warnings = [v for v in result.schema_violations if v.severity == "WARNING"]
        if warnings:
            sys.exit(1)


# ---------------------------------------------------------------------------
# infer
# ---------------------------------------------------------------------------


@main.command()
@click.argument("data_path", metavar="DATA")
@click.option("--name", required=True, help="Contract name (e.g. 'transactions').")
@click.option("--version", default="1.0.0", show_default=True, help="Contract version.")
@click.option(
    "--output",
    required=True,
    metavar="PATH",
    help="Output YAML file path.",
)
@click.option(
    "--owner",
    default=None,
    help="Contract owner email or team name.",
)
@click.option(
    "--description",
    default=None,
    help="Human-readable description of the dataset.",
)
def infer(
    data_path: str,
    name: str,
    version: str,
    output: str,
    owner: str,
    description: str,
) -> None:
    """Infer a contract schema from a DATA file.

    Supports CSV and Parquet formats. Writes the inferred contract to OUTPUT.

    Example:

        datalasi infer data/transactions.parquet --name transactions --output contracts/tx-v1.0.0.yaml
    """
    try:
        df = _load_data(data_path)
    except Exception as exc:
        click.echo(click.style(f"Error loading data: {exc}", fg="red"), err=True)
        sys.exit(2)

    try:
        import pandas as pd

        from datalasi.adapters.pandas_adapter import PandasAdapter

        if not isinstance(df, pd.DataFrame):
            click.echo(
                click.style(
                    "Error: 'infer' currently requires a Pandas-compatible data file.", fg="red"
                ),
                err=True,
            )
            sys.exit(2)

        schema = PandasAdapter.infer_schema(df)
    except ImportError:
        click.echo(
            click.style(
                "Error: pandas is required for 'infer'. Run: pip install 'datalasi[pandas]'",
                fg="red",
            ),
            err=True,
        )
        sys.exit(2)

    from datalasi.core.contract import DataContract
    from datalasi.io.writers import YAMLWriter

    contract = DataContract(
        name=name,
        version=version,
        schema=schema,
        owner=owner,
        description=description,
    )

    YAMLWriter.write(contract, output)
    click.echo(
        click.style("✓ Contract inferred", fg="green")
        + f"  {name} v{version}  →  {output}"
        + f"  ({len(schema)} column(s))"
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@main.command(name="list")
@click.option(
    "--registry",
    default="contracts",
    show_default=True,
    metavar="DIR",
    help="Path to the contracts registry directory.",
)
def list_contracts(registry: str) -> None:
    """List all contracts and versions in a registry directory.

    Example:

        datalasi list --registry contracts/
    """
    from datalasi.cli.formatters import print_registry
    from datalasi.io.registry import ContractRegistry

    reg = ContractRegistry(registry)
    contracts = reg.list_contracts()

    if not contracts:
        click.echo(f"No contracts found in {registry!r}.")
        return

    print_registry(contracts)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


@main.command()
@click.argument("registry_dir", metavar="REGISTRY")
@click.argument("contract_name", metavar="NAME")
@click.argument("v1")
@click.argument("v2")
def diff(registry_dir: str, contract_name: str, v1: str, v2: str) -> None:
    """Show schema changes between two contract versions.

    REGISTRY is the contracts directory. NAME is the contract name.
    V1 and V2 are version strings (e.g. 1.0.0 and 1.1.0).

    Exit code: 0 if no breaking changes, 1 if breaking changes detected.

    Example:

        datalasi diff contracts/ transactions 1.0.0 1.1.0
    """
    from datalasi.cli.formatters import print_diff
    from datalasi.errors import ContractNotFoundError
    from datalasi.io.registry import ContractRegistry

    try:
        registry = ContractRegistry(registry_dir)
        contract_diff = registry.diff(contract_name, v1, v2)
    except ContractNotFoundError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(2)

    print_diff(contract_diff)

    if contract_diff.has_breaking_changes:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_data(path: str) -> object:
    """Load a CSV or Parquet file as a Pandas DataFrame.

    Raises:
        ImportError: if pandas is not installed.
        ValueError: if the file format is not supported.
        FileNotFoundError: if the file does not exist.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    import pandas as pd

    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported file format: {suffix!r}. Supported: .csv, .parquet, .json")
