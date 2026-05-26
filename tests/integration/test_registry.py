"""Integration tests for the contract registry and breaking change detection."""

import pytest

from datalasi import DataContract, Enum, Field, Float64, Int64, String
from datalasi.errors import ContractNotFoundError
from datalasi.io.registry import ContractDiff, ContractRegistry, _detect_changes
from datalasi.io.writers import YAMLWriter


def _write(contract, tmp_path, filename):
    path = str(tmp_path / filename)
    YAMLWriter.write(contract, path)
    return path


def _v1(tmp_path):
    c = DataContract(
        name="transactions",
        version="1.0.0",
        schema={
            "id": Field("id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.0, max=1_000_000), nullable=False),
            "status": Field("status", Enum(["PENDING", "COMPLETED", "FAILED"]), nullable=False),
            "note": Field("note", String(max_length=500)),
        },
        expectations=["amount > 0"],
    )
    _write(c, tmp_path, "tx-v1.0.0.yaml")
    return c


def _v2(tmp_path):
    # Breaking: amount.min raised 0→0.01, status removed FAILED
    # Non-breaking: currency column added, nullable changed non-null→null on amount
    c = DataContract(
        name="transactions",
        version="1.1.0",
        schema={
            "id": Field("id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01, max=1_000_000), nullable=True),
            "status": Field("status", Enum(["PENDING", "COMPLETED"]), nullable=False),
            "note": Field("note", String(max_length=500)),
            "currency": Field("currency", String()),
        },
    )
    _write(c, tmp_path, "tx-v1.1.0.yaml")
    return c


def _v3(tmp_path):
    # Breaking: id column removed, amount type changed to String
    c = DataContract(
        name="transactions",
        version="2.0.0",
        schema={
            "amount": Field("amount", String(), nullable=False),
            "status": Field("status", Enum(["PENDING", "COMPLETED"]), nullable=False),
        },
    )
    _write(c, tmp_path, "tx-v2.0.0.yaml")
    return c


class TestContractRegistry:
    def test_load_single_contract(self, tmp_path):
        _v1(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        assert len(reg) == 1

    def test_load_multiple_contracts(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        _v3(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        assert len(reg) == 3

    def test_get_latest_version(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        latest = reg.get("transactions")
        assert latest.version == "1.1.0"

    def test_get_latest_with_three_versions(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        _v3(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        latest = reg.get("transactions")
        assert latest.version == "2.0.0"

    def test_get_specific_version(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        v1 = reg.get("transactions", version="1.0.0")
        assert v1.version == "1.0.0"

    def test_get_unknown_name_raises(self, tmp_path):
        _v1(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        with pytest.raises(ContractNotFoundError):
            reg.get("nonexistent")

    def test_get_unknown_version_raises(self, tmp_path):
        _v1(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        with pytest.raises(ContractNotFoundError):
            reg.get("transactions", version="9.9.9")

    def test_list_contracts(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        listing = reg.list_contracts()
        assert "transactions" in listing
        assert "1.0.0" in listing["transactions"]
        assert "1.1.0" in listing["transactions"]

    def test_list_versions_sorted(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        _v3(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        versions = reg.list_contracts()["transactions"]
        assert versions == ["1.0.0", "1.1.0", "2.0.0"]

    def test_empty_registry_dir(self, tmp_path):
        reg = ContractRegistry(str(tmp_path))
        assert len(reg) == 0

    def test_nonexistent_dir(self, tmp_path):
        reg = ContractRegistry(str(tmp_path / "missing"))
        assert len(reg) == 0

    def test_repr(self, tmp_path):
        reg = ContractRegistry(str(tmp_path))
        assert "ContractRegistry" in repr(reg)

    def test_reload(self, tmp_path):
        reg = ContractRegistry(str(tmp_path))
        assert len(reg) == 0
        _v1(tmp_path)
        reg.reload()
        assert len(reg) == 1

    def test_multiple_contract_names(self, tmp_path):
        _v1(tmp_path)
        other = DataContract(name="users", version="1.0.0", schema={})
        _write(other, tmp_path, "users-v1.yaml")
        reg = ContractRegistry(str(tmp_path))
        listing = reg.list_contracts()
        assert "transactions" in listing
        assert "users" in listing


class TestBreakingChanges:
    def test_no_changes(self, tmp_path):
        v1 = _v1(tmp_path)
        v1_copy = DataContract.from_dict({**v1.to_dict(), "version": "1.0.1"})
        _write(v1_copy, tmp_path, "tx-v1.0.1.yaml")
        reg = ContractRegistry(str(tmp_path))
        breaking = reg.breaking_changes_between("transactions", "1.0.0", "1.0.1")
        assert breaking == []

    def test_column_removed_is_breaking(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        _v3(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        breaking = reg.breaking_changes_between("transactions", "1.0.0", "2.0.0")
        assert any("id" in c and "removed" in c for c in breaking)

    def test_type_change_is_breaking(self, tmp_path):
        _v1(tmp_path)
        _v3(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        breaking = reg.breaking_changes_between("transactions", "1.0.0", "2.0.0")
        assert any("amount" in c and "type" in c for c in breaking)

    def test_min_tightened_is_breaking(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        breaking = reg.breaking_changes_between("transactions", "1.0.0", "1.1.0")
        assert any("amount" in c and "min" in c for c in breaking)

    def test_enum_value_removed_is_breaking(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        breaking = reg.breaking_changes_between("transactions", "1.0.0", "1.1.0")
        assert any("FAILED" in c for c in breaking)

    def test_column_added_is_non_breaking(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        diff = reg.diff("transactions", "1.0.0", "1.1.0")
        assert any("currency" in c for c in diff.non_breaking_changes)

    def test_nullable_to_nonnullable_is_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"x": Field("x", Int64(), nullable=True)},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"x": Field("x", Int64(), nullable=False)},
        )
        breaking, _ = _detect_changes(old, new)
        assert any("non-nullable" in c for c in breaking)

    def test_nonnullable_to_nullable_is_non_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"x": Field("x", Int64(), nullable=False)},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"x": Field("x", Int64(), nullable=True)},
        )
        breaking, non_breaking = _detect_changes(old, new)
        assert breaking == []
        assert any("nullable" in c for c in non_breaking)

    def test_max_decreased_is_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"x": Field("x", Float64(max=1000.0))},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"x": Field("x", Float64(max=100.0))},
        )
        breaking, _ = _detect_changes(old, new)
        assert any("max" in c for c in breaking)

    def test_max_increased_is_non_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"x": Field("x", Float64(max=100.0))},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"x": Field("x", Float64(max=1000.0))},
        )
        breaking, non_breaking = _detect_changes(old, new)
        assert breaking == []

    def test_string_max_length_decreased_is_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"s": Field("s", String(max_length=500))},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"s": Field("s", String(max_length=100))},
        )
        breaking, _ = _detect_changes(old, new)
        assert any("max_length" in c for c in breaking)

    def test_enum_value_added_is_non_breaking(self):
        old = DataContract(
            name="t",
            version="1.0.0",
            schema={"s": Field("s", Enum(["A", "B"]))},
        )
        new = DataContract(
            name="t",
            version="1.1.0",
            schema={"s": Field("s", Enum(["A", "B", "C"]))},
        )
        breaking, non_breaking = _detect_changes(old, new)
        assert breaking == []
        assert any("C" in c for c in non_breaking)


class TestContractDiff:
    def test_diff_has_breaking_changes(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        diff = reg.diff("transactions", "1.0.0", "1.1.0")
        assert isinstance(diff, ContractDiff)
        assert diff.has_breaking_changes

    def test_diff_summary_string(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        diff = reg.diff("transactions", "1.0.0", "1.1.0")
        assert "transactions" in diff.summary
        assert "1.0.0" in diff.summary

    def test_diff_str(self, tmp_path):
        _v1(tmp_path)
        _v2(tmp_path)
        reg = ContractRegistry(str(tmp_path))
        diff = reg.diff("transactions", "1.0.0", "1.1.0")
        s = str(diff)
        assert "Breaking" in s or "Non-breaking" in s
