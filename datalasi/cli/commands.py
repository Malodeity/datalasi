"""datalasi CLI entry point.

Commands:
  validate  — validate a CSV/Parquet file against a contract
  infer     — infer a contract schema from a data file
  init      — interactively create a new contract YAML
  list      — list contracts in a registry directory
  diff      — show breaking/non-breaking changes between two contract versions
  check     — check for breaking changes against the previous version (CI gate)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
# init
# ---------------------------------------------------------------------------

_SUPPORTED_TYPES = ["Int64", "Int32", "Float64", "String", "Boolean", "Date", "Timestamp", "Enum"]


@main.command()
@click.option("--output", default=None, metavar="PATH", help="Output YAML file path.")
def init(output: str | None) -> None:
    """Interactively create a new data contract YAML file.

    Walks through prompts to define the contract name, version, columns,
    and expectations, then writes the result to a YAML file.

    Example:

        datalasi init
        datalasi init --output contracts/orders-v1.0.0.yaml
    """
    from datalasi.core.contract import DataContract, Field
    from datalasi.core.types import (
        TYPE_REGISTRY,
        Enum,
        String,
        Timestamp,
    )
    from datalasi.io.writers import YAMLWriter

    click.echo(click.style("datalasi — new contract wizard", bold=True))
    click.echo()

    name = click.prompt("Contract name (e.g. orders)")
    version = click.prompt("Version", default="1.0.0")
    owner = click.prompt("Owner email / team (optional)", default="", show_default=False)
    description = click.prompt("Description (optional)", default="", show_default=False)

    click.echo()
    click.echo("Define columns (press Enter with an empty name to finish):")

    schema: dict[str, Field] = {}
    while True:
        click.echo()
        col_name = click.prompt("  Column name", default="", show_default=False).strip()
        if not col_name:
            if not schema:
                click.echo(click.style("  At least one column is required.", fg="yellow"))
                continue
            break

        type_choices = "/".join(_SUPPORTED_TYPES)
        type_name = click.prompt(f"  Type [{type_choices}]", default="String")
        while type_name not in _SUPPORTED_TYPES:
            click.echo(click.style(f"  Unknown type. Choose from: {type_choices}", fg="yellow"))
            type_name = click.prompt(f"  Type [{type_choices}]", default="String")

        # Type-specific options
        col_type: Any
        if type_name == "Enum":
            raw = click.prompt("  Allowed values (comma-separated)")
            allowed = [v.strip() for v in raw.split(",") if v.strip()]
            col_type = Enum(allowed)
        elif type_name in ("Int64", "Int32", "Float64"):
            min_val = click.prompt("  Min value (optional)", default="", show_default=False)
            max_val = click.prompt("  Max value (optional)", default="", show_default=False)
            kw: dict[str, Any] = {}
            if min_val:
                kw["min"] = float(min_val) if type_name == "Float64" else int(min_val)
            if max_val:
                kw["max"] = float(max_val) if type_name == "Float64" else int(max_val)
            col_type = TYPE_REGISTRY[type_name].from_dict({**kw, "type": type_name})
        elif type_name == "String":
            max_len = click.prompt("  Max length (optional)", default="", show_default=False)
            pattern = click.prompt("  Regex pattern (optional)", default="", show_default=False)
            col_type = String(
                max_length=int(max_len) if max_len else None,
                pattern=pattern or None,
            )
        elif type_name == "Timestamp":
            tz = click.prompt("  Timezone (optional, e.g. UTC)", default="", show_default=False)
            col_type = Timestamp(timezone=tz or None)
        else:
            col_type = TYPE_REGISTRY[type_name].from_dict({"type": type_name})

        nullable = click.confirm("  Nullable?", default=True)
        pk = click.confirm("  Primary key?", default=False)
        col_desc = click.prompt("  Description (optional)", default="", show_default=False)

        schema[col_name] = Field(
            name=col_name,
            type=col_type,
            nullable=nullable,
            pk=pk,
            description=col_desc or None,
        )
        click.echo(click.style(f"  ✓ {col_name} ({type_name})", fg="green"))

    click.echo()
    click.echo("Add data-quality expectations (press Enter to skip):")
    expectations: list[str] = []
    while True:
        exp = click.prompt(
            '  Expectation (e.g. "amount > 0")', default="", show_default=False
        ).strip()
        if not exp:
            break
        expectations.append(exp)
        click.echo(click.style(f"  ✓ {exp!r}", fg="green"))

    contract = DataContract(
        name=name,
        version=version,
        schema=schema,
        expectations=expectations,
        owner=owner or None,
        description=description or None,
    )

    if output is None:
        default_path = f"contracts/{name}-v{version}.yaml"
        output = click.prompt("Output file", default=default_path)

    YAMLWriter.write(contract, output)
    click.echo()
    click.echo(
        click.style("✓ Contract written: ", fg="green")
        + f"{name} v{version} → {output}"
        + f"  ({len(schema)} column(s), {len(expectations)} expectation(s))"
    )


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
# check
# ---------------------------------------------------------------------------


@main.command()
@click.argument("registry_dir", metavar="REGISTRY")
@click.argument("contract_name", metavar="NAME")
@click.argument("version", required=False, default=None)
def check(registry_dir: str, contract_name: str, version: str | None) -> None:
    """CI gate — check a contract version for breaking changes vs its predecessor.

    REGISTRY is the contracts directory. NAME is the contract name.
    VERSION defaults to the latest version in the registry.

    Exit code: 0 if no breaking changes, 1 if breaking changes detected, 2 on error.

    Typical CI usage (fail the pipeline on breaking changes):

        datalasi check contracts/ transactions

    Check a specific version against its predecessor:

        datalasi check contracts/ transactions 1.2.0
    """
    from datalasi.cli.formatters import print_diff
    from datalasi.errors import ContractNotFoundError
    from datalasi.io.registry import ContractRegistry

    try:
        registry = ContractRegistry(registry_dir)
        all_versions = registry.list_contracts().get(contract_name, [])
    except Exception as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(2)

    if not all_versions:
        click.echo(
            click.style(f"Error: No contract named {contract_name!r} found.", fg="red"), err=True
        )
        sys.exit(2)

    if len(all_versions) < 2:
        click.echo(f"Only one version ({all_versions[0]}) exists — nothing to compare.")
        sys.exit(0)

    if version is None:
        v2 = all_versions[-1]
        v1 = all_versions[-2]
    else:
        if version not in all_versions:
            click.echo(
                click.style(
                    f"Error: version {version!r} not found. Available: {all_versions}", fg="red"
                ),
                err=True,
            )
            sys.exit(2)
        idx = all_versions.index(version)
        if idx == 0:
            click.echo(f"Version {version} is the oldest — nothing to compare.")
            sys.exit(0)
        v2 = version
        v1 = all_versions[idx - 1]

    try:
        contract_diff = registry.diff(contract_name, v1, v2)
    except ContractNotFoundError as exc:
        click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
        sys.exit(2)

    print_diff(contract_diff)

    if contract_diff.has_breaking_changes:
        sys.exit(1)


# ---------------------------------------------------------------------------
# dbt
# ---------------------------------------------------------------------------


@main.command()
@click.argument("contract_path", metavar="CONTRACT")
@click.option(
    "--output",
    default=None,
    metavar="PATH",
    help="Output YAML file path. Defaults to stdout.",
)
@click.option("--model-name", default=None, help="Override the dbt model name.")
@click.option(
    "--source",
    default=None,
    metavar="SOURCE_NAME",
    help="Wrap in a sources block with this source name.",
)
def dbt(contract_path: str, output: str | None, model_name: str | None, source: str | None) -> None:
    """Generate a dbt schema.yml from a contract.

    CONTRACT is a path to a YAML contract file.

    Writes a ready-to-use dbt schema file with not_null, unique,
    accepted_values, and dbt_utils constraint tests.

    Examples:

        datalasi dbt contracts/transactions-v1.0.0.yaml

        datalasi dbt contracts/orders-v1.0.0.yaml --output models/staging/schema.yml

        datalasi dbt contracts/orders-v1.0.0.yaml --source raw_postgres
    """
    from datalasi.errors import ContractLoadError
    from datalasi.export.dbt import to_dbt_schema_yaml
    from datalasi.io.loaders import YAMLLoader

    try:
        contract = YAMLLoader.load(contract_path)
    except FileNotFoundError:
        click.echo(click.style(f"Error: contract not found: {contract_path}", fg="red"), err=True)
        sys.exit(2)
    except ContractLoadError as exc:
        click.echo(click.style(f"Error loading contract: {exc}", fg="red"), err=True)
        sys.exit(2)

    yaml_str = to_dbt_schema_yaml(contract, model_name=model_name, source_name=source)

    if output:
        from pathlib import Path

        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(yaml_str)
        click.echo(
            click.style("✓ dbt schema written: ", fg="green") + f"{contract.name} → {output}"
        )
    else:
        click.echo(yaml_str)


# ---------------------------------------------------------------------------
# pydantic
# ---------------------------------------------------------------------------


@main.command()
@click.argument("contract_path", metavar="CONTRACT")
@click.option(
    "--output",
    default=None,
    metavar="PATH",
    help="Output .py file path. Defaults to stdout.",
)
def pydantic(contract_path: str, output: str | None) -> None:
    """Generate a Pydantic BaseModel from a contract.

    CONTRACT is a path to a YAML contract file.

    Produces a Python source file with a Pydantic v2 BaseModel class,
    type annotations, and field validators derived from the contract schema.

    Examples:

        datalasi pydantic contracts/transactions-v1.0.0.yaml

        datalasi pydantic contracts/orders-v1.0.0.yaml --output models/orders.py
    """
    from datalasi.errors import ContractLoadError
    from datalasi.export.pydantic_model import to_pydantic_source
    from datalasi.io.loaders import YAMLLoader

    try:
        contract = YAMLLoader.load(contract_path)
    except FileNotFoundError:
        click.echo(click.style(f"Error: contract not found: {contract_path}", fg="red"), err=True)
        sys.exit(2)
    except ContractLoadError as exc:
        click.echo(click.style(f"Error loading contract: {exc}", fg="red"), err=True)
        sys.exit(2)

    source = to_pydantic_source(contract)

    if output:
        from pathlib import Path

        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(source)
        click.echo(
            click.style("✓ Pydantic model written: ", fg="green") + f"{contract.name} → {output}"
        )
    else:
        click.echo(source)


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
