"""Unit tests for YAML I/O layer."""

import pytest

from datalasi import DataContract, Enum, Field, Float64, Int64, String
from datalasi.errors import ContractLoadError
from datalasi.io import YAMLLoader, YAMLWriter


def _make_contract():
    return DataContract(
        name="orders",
        version="1.0.0",
        schema={
            "order_id": Field("order_id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01), nullable=False),
            "status": Field(
                "status",
                Enum(["OPEN", "CLOSED", "CANCELLED"]),
                nullable=False,
            ),
            "note": Field("note", String(max_length=500)),
        },
        expectations=["amount > 0"],
        breaking_changes="WARN",
        owner="orders-team@example.com",
        description="Customer orders",
        tags={"pii": "false"},
    )


class TestYAMLWriter:
    def test_write_creates_file(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "orders.yaml")
        YAMLWriter.write(contract, path)
        assert (tmp_path / "orders.yaml").exists()

    def test_write_creates_parent_dirs(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "nested" / "dir" / "orders.yaml")
        YAMLWriter.write(contract, path)
        assert (tmp_path / "nested" / "dir" / "orders.yaml").exists()

    def test_write_produces_valid_yaml(self, tmp_path):
        import yaml

        contract = _make_contract()
        path = str(tmp_path / "out.yaml")
        YAMLWriter.write(contract, path)

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        assert raw["name"] == "orders"
        assert raw["version"] == "1.0.0"

    def test_write_schema_fields_serialized(self, tmp_path):
        import yaml

        contract = _make_contract()
        path = str(tmp_path / "out.yaml")
        YAMLWriter.write(contract, path)

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        assert "order_id" in raw["schema"]
        assert raw["schema"]["order_id"]["type"] == "Int64"
        assert raw["schema"]["amount"]["min"] == pytest.approx(0.01)

    def test_write_enum_values_preserved(self, tmp_path):
        import yaml

        contract = _make_contract()
        path = str(tmp_path / "out.yaml")
        YAMLWriter.write(contract, path)

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        assert raw["schema"]["status"]["allowed_values"] == ["OPEN", "CLOSED", "CANCELLED"]


class TestYAMLLoader:
    def test_load_basic(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "orders.yaml")
        YAMLWriter.write(contract, path)

        loaded = YAMLLoader.load(path)
        assert loaded.name == "orders"
        assert loaded.version == "1.0.0"

    def test_load_schema_types(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "out.yaml")
        YAMLWriter.write(contract, path)

        loaded = YAMLLoader.load(path)
        assert isinstance(loaded.schema["order_id"].type, Int64)
        assert isinstance(loaded.schema["amount"].type, Float64)
        assert isinstance(loaded.schema["status"].type, Enum)
        assert isinstance(loaded.schema["note"].type, String)

    def test_load_metadata(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "out.yaml")
        YAMLWriter.write(contract, path)

        loaded = YAMLLoader.load(path)
        assert loaded.owner == "orders-team@example.com"
        assert loaded.description == "Customer orders"
        assert loaded.tags == {"pii": "false"}
        assert loaded.breaking_changes == "WARN"
        assert loaded.expectations == ["amount > 0"]

    def test_load_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            YAMLLoader.load(str(tmp_path / "missing.yaml"))

    def test_load_malformed_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("name: [\nbad yaml content{{{{")
        with pytest.raises(ContractLoadError):
            YAMLLoader.load(str(bad_file))

    def test_load_missing_required_key(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("version: 1.0.0\n")  # missing 'name'
        with pytest.raises(ContractLoadError):
            YAMLLoader.load(str(bad_file))

    def test_load_non_mapping_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("- item1\n- item2\n")
        with pytest.raises(ContractLoadError):
            YAMLLoader.load(str(bad_file))


class TestRoundtrip:
    def test_write_then_load_identity(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "rt.yaml")

        YAMLWriter.write(contract, path)
        loaded = YAMLLoader.load(path)

        assert loaded == contract

    def test_roundtrip_preserves_field_constraints(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "rt.yaml")
        YAMLWriter.write(contract, path)
        loaded = YAMLLoader.load(path)

        assert loaded.schema["amount"].type.min == pytest.approx(0.01)
        assert loaded.schema["note"].type.max_length == 500

    def test_roundtrip_preserves_nullability(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "rt.yaml")
        YAMLWriter.write(contract, path)
        loaded = YAMLLoader.load(path)

        assert loaded.schema["order_id"].nullable is False
        assert loaded.schema["note"].nullable is True

    def test_roundtrip_preserves_pk(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "rt.yaml")
        YAMLWriter.write(contract, path)
        loaded = YAMLLoader.load(path)

        assert loaded.schema["order_id"].pk is True
        assert loaded.schema["amount"].pk is False

    def test_contract_save_and_load_helpers(self, tmp_path):
        contract = _make_contract()
        path = str(tmp_path / "orders.yaml")

        contract.save(path)
        loaded = DataContract.load(path)

        assert loaded == contract

    def test_roundtrip_empty_contract(self, tmp_path, empty_contract):
        path = str(tmp_path / "empty.yaml")
        YAMLWriter.write(empty_contract, path)
        loaded = YAMLLoader.load(path)
        assert loaded == empty_contract

    def test_multiple_roundtrips_stable(self, tmp_path):
        contract = _make_contract()
        for i in range(3):
            path = str(tmp_path / f"v{i}.yaml")
            YAMLWriter.write(contract, path)
            contract = YAMLLoader.load(path)

        assert contract.name == "orders"
        assert contract.version == "1.0.0"


class TestYAMLFromFile:
    """Test loading from hand-crafted YAML (the format users actually write)."""

    def test_load_hand_written_yaml(self, tmp_path):
        yaml_content = """\
name: transactions
version: 1.0.0
owner: data-eng@company.com
description: Financial transactions from payment gateway
breaking_changes: FAIL

schema:
  transaction_id:
    type: Int64
    nullable: false
    pk: true
    description: Unique transaction ID

  amount:
    type: Float64
    nullable: false
    min: 0.01
    max: 1000000

  status:
    type: Enum
    allowed_values: [PENDING, COMPLETED, FAILED, REFUNDED]
    nullable: false

  timestamp:
    type: Timestamp
    nullable: false

expectations:
  - "amount > 0"
  - "status IN ['PENDING', 'COMPLETED', 'FAILED', 'REFUNDED']"
"""
        yaml_file = tmp_path / "transactions.yaml"
        yaml_file.write_text(yaml_content)

        contract = YAMLLoader.load(str(yaml_file))

        assert contract.name == "transactions"
        assert contract.version == "1.0.0"
        assert contract.owner == "data-eng@company.com"
        assert contract.breaking_changes == "FAIL"
        assert len(contract.schema) == 4
        assert contract.schema["transaction_id"].pk is True
        assert contract.schema["transaction_id"].nullable is False
        assert isinstance(contract.schema["amount"].type, Float64)
        assert contract.schema["amount"].type.min == pytest.approx(0.01)
        assert isinstance(contract.schema["status"].type, Enum)
        assert "PENDING" in contract.schema["status"].type.allowed_values
        assert len(contract.expectations) == 2
