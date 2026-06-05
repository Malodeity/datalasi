"""Integration tests for the datalasi CLI."""

import pytest
from click.testing import CliRunner

from datalasi import DataContract, Enum, Field, Float64, Int64, String
from datalasi.cli.commands import main
from datalasi.io.writers import YAMLWriter


def _make_contract(name="orders", version="1.0.0"):
    return DataContract(
        name=name,
        version=version,
        schema={
            "id": Field("id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01), nullable=False),
            "status": Field("status", Enum(["OPEN", "CLOSED"]), nullable=False),
        },
        expectations=["amount > 0"],
    )


pytest.importorskip("pandas")
import pandas as pd  # noqa: E402


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def contract_file(tmp_path):
    contract = _make_contract()
    path = str(tmp_path / "orders.yaml")
    YAMLWriter.write(contract, path)
    return path


@pytest.fixture
def valid_csv(tmp_path):
    df = pd.DataFrame(
        {"id": [1, 2, 3], "amount": [10.0, 20.0, 30.0], "status": ["OPEN", "CLOSED", "OPEN"]}
    )
    path = str(tmp_path / "data.csv")
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def invalid_csv(tmp_path):
    df = pd.DataFrame(
        {"id": [1, 2, 3], "amount": [-5.0, 20.0, 30.0], "status": ["OPEN", "CLOSED", "OPEN"]}
    )
    path = str(tmp_path / "bad.csv")
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_pass_exit_zero(self, runner, contract_file, valid_csv):
        result = runner.invoke(main, ["validate", contract_file, valid_csv])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_fail_exit_one(self, runner, contract_file, invalid_csv):
        result = runner.invoke(main, ["validate", contract_file, invalid_csv])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_missing_contract_exit_two(self, runner, valid_csv):
        result = runner.invoke(main, ["validate", "/no/such/file.yaml", valid_csv])
        assert result.exit_code == 2

    def test_missing_data_exit_two(self, runner, contract_file):
        result = runner.invoke(main, ["validate", contract_file, "/no/such/data.csv"])
        assert result.exit_code == 2

    def test_output_includes_row_count(self, runner, contract_file, valid_csv):
        result = runner.invoke(main, ["validate", contract_file, valid_csv])
        assert "3" in result.output

    def test_violation_details_shown_on_fail(self, runner, contract_file, invalid_csv):
        result = runner.invoke(main, ["validate", contract_file, invalid_csv])
        # Expectation violation for amount > 0 should be reported
        assert "amount" in result.output


# ---------------------------------------------------------------------------
# infer command
# ---------------------------------------------------------------------------


class TestInferCommand:
    def test_creates_yaml_file(self, runner, tmp_path, valid_csv):
        output = str(tmp_path / "inferred.yaml")
        result = runner.invoke(
            main,
            ["infer", valid_csv, "--name", "orders", "--output", output],
        )
        assert result.exit_code == 0
        import os

        assert os.path.exists(output)

    def test_inferred_contract_loadable(self, runner, tmp_path, valid_csv):
        output = str(tmp_path / "inferred.yaml")
        runner.invoke(main, ["infer", valid_csv, "--name", "mydata", "--output", output])
        from datalasi.io.loaders import YAMLLoader

        contract = YAMLLoader.load(output)
        assert contract.name == "mydata"
        assert contract.version == "1.0.0"

    def test_infer_custom_version(self, runner, tmp_path, valid_csv):
        output = str(tmp_path / "inferred.yaml")
        result = runner.invoke(
            main,
            ["infer", valid_csv, "--name", "d", "--version", "2.0.0", "--output", output],
        )
        assert result.exit_code == 0
        from datalasi.io.loaders import YAMLLoader

        contract = YAMLLoader.load(output)
        assert contract.version == "2.0.0"

    def test_infer_missing_file_exit_two(self, runner, tmp_path):
        result = runner.invoke(
            main,
            ["infer", "/missing.csv", "--name", "x", "--output", str(tmp_path / "out.yaml")],
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# list command
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_empty_registry(self, runner, tmp_path):
        result = runner.invoke(main, ["list", "--registry", str(tmp_path)])
        assert result.exit_code == 0
        assert "No contracts" in result.output

    def test_list_shows_contract_names(self, runner, tmp_path):
        WYAMLWriter = YAMLWriter
        WYAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "orders-1.yaml"))
        WYAMLWriter.write(_make_contract("users", "1.0.0"), str(tmp_path / "users-1.yaml"))
        result = runner.invoke(main, ["list", "--registry", str(tmp_path)])
        assert result.exit_code == 0
        assert "orders" in result.output
        assert "users" in result.output

    def test_list_shows_versions(self, runner, tmp_path):
        WYAMLWriter = YAMLWriter
        WYAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "orders-v1.yaml"))
        WYAMLWriter.write(_make_contract("orders", "1.1.0"), str(tmp_path / "orders-v2.yaml"))
        result = runner.invoke(main, ["list", "--registry", str(tmp_path)])
        assert "1.0.0" in result.output
        assert "1.1.0" in result.output


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


class TestDiffCommand:
    def test_no_changes_exit_zero(self, runner, tmp_path):
        YAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "v1.yaml"))
        # Identical schema, different version
        c2 = DataContract.from_dict({**_make_contract("orders", "1.0.1").to_dict()})
        YAMLWriter.write(c2, str(tmp_path / "v101.yaml"))
        result = runner.invoke(main, ["diff", str(tmp_path), "orders", "1.0.0", "1.0.1"])
        assert result.exit_code == 0

    def test_breaking_changes_exit_one(self, runner, tmp_path):
        YAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "v1.yaml"))
        # Remove a column — breaking
        c2 = DataContract(
            name="orders",
            version="2.0.0",
            schema={"id": Field("id", Int64(), nullable=False)},
        )
        YAMLWriter.write(c2, str(tmp_path / "v2.yaml"))
        result = runner.invoke(main, ["diff", str(tmp_path), "orders", "1.0.0", "2.0.0"])
        assert result.exit_code == 1

    def test_missing_version_exit_two(self, runner, tmp_path):
        YAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "v1.yaml"))
        result = runner.invoke(main, ["diff", str(tmp_path), "orders", "1.0.0", "9.9.9"])
        assert result.exit_code == 2

    def test_diff_output_shows_changes(self, runner, tmp_path):
        YAMLWriter.write(_make_contract("orders", "1.0.0"), str(tmp_path / "v1.yaml"))
        c2 = DataContract(
            name="orders",
            version="1.1.0",
            schema={
                "id": Field("id", Int64(), nullable=False),
                "amount": Field("amount", Float64(min=0.01), nullable=False),
                "status": Field("status", Enum(["OPEN", "CLOSED"]), nullable=False),
                "note": Field("note", String()),  # new column
            },
        )
        YAMLWriter.write(c2, str(tmp_path / "v2.yaml"))
        result = runner.invoke(main, ["diff", str(tmp_path), "orders", "1.0.0", "1.1.0"])
        assert "note" in result.output


# ---------------------------------------------------------------------------
# Version flag
# ---------------------------------------------------------------------------


def test_version_flag(runner):
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.output


def test_help(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
    assert "infer" in result.output
    assert "list" in result.output
    assert "diff" in result.output


# ---------------------------------------------------------------------------
# check command
# ---------------------------------------------------------------------------


class TestCheck:
    def _write_two_versions(self, tmp_path):
        from datalasi.io.writers import YAMLWriter

        v1 = _make_contract(version="1.0.0")
        v2 = _make_contract(version="1.1.0")
        v2.schema["new_col"] = Field("new_col", String())  # non-breaking addition
        YAMLWriter.write(v1, str(tmp_path / "orders-v1.0.0.yaml"))
        YAMLWriter.write(v2, str(tmp_path / "orders-v1.1.0.yaml"))
        return tmp_path

    def test_no_breaking_changes_exits_zero(self, runner, tmp_path):
        self._write_two_versions(tmp_path)
        result = runner.invoke(main, ["check", str(tmp_path), "orders"])
        assert result.exit_code == 0

    def test_breaking_change_exits_one(self, runner, tmp_path):
        from datalasi.core.contract import DataContract
        from datalasi.io.writers import YAMLWriter

        v1 = _make_contract(version="1.0.0")
        v2 = DataContract(
            name="orders",
            version="2.0.0",
            schema={
                "id": Field("id", Int64(), nullable=False),
                # amount removed — breaking!
            },
        )
        YAMLWriter.write(v1, str(tmp_path / "v1.yaml"))
        YAMLWriter.write(v2, str(tmp_path / "v2.yaml"))
        result = runner.invoke(main, ["check", str(tmp_path), "orders"])
        assert result.exit_code == 1

    def test_only_one_version_exits_zero(self, runner, tmp_path):
        from datalasi.io.writers import YAMLWriter

        YAMLWriter.write(_make_contract(), str(tmp_path / "v1.yaml"))
        result = runner.invoke(main, ["check", str(tmp_path), "orders"])
        assert result.exit_code == 0
        assert "Only one version" in result.output

    def test_unknown_contract_exits_two(self, runner, tmp_path):
        result = runner.invoke(main, ["check", str(tmp_path), "nonexistent"])
        assert result.exit_code == 2

    def test_specific_version(self, runner, tmp_path):
        self._write_two_versions(tmp_path)
        result = runner.invoke(main, ["check", str(tmp_path), "orders", "1.1.0"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_file(self, runner, tmp_path):
        output = str(tmp_path / "out.yaml")
        inputs = "\n".join(
            [
                "mycontract",  # name
                "1.0.0",  # version
                "",  # owner (skip)
                "",  # description (skip)
                "price",  # column name
                "Float64",  # type
                "",  # min
                "",  # max
                "N",  # nullable
                "N",  # pk
                "",  # col description
                "",  # stop adding columns
                "",  # stop adding expectations
                output,  # output path
            ]
        )
        result = runner.invoke(main, ["init"], input=inputs)
        assert result.exit_code == 0, result.output
        from datalasi.io.loaders import YAMLLoader

        contract = YAMLLoader.load(output)
        assert contract.name == "mycontract"
        assert "price" in contract.schema

    def test_init_output_flag(self, runner, tmp_path):
        output = str(tmp_path / "flagged.yaml")
        inputs = "\n".join(
            [
                "flagcontract",
                "1.0.0",
                "",
                "",
                "x",
                "String",
                "",
                "",
                "Y",
                "N",
                "",
                "",
                "",
            ]
        )
        result = runner.invoke(main, ["init", "--output", output], input=inputs)
        assert result.exit_code == 0, result.output
        import os

        assert os.path.exists(output)
