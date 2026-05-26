"""Unit tests for DataContract and Field."""

import pytest

from datalasi import DataContract, Field, Float64, Int64, String, Enum, Timestamp
from datalasi.core.types import Boolean


class TestField:
    def test_create_basic_field(self):
        f = Field("amount", Float64(min=0))
        assert f.name == "amount"
        assert isinstance(f.type, Float64)
        assert f.nullable is True
        assert f.pk is False

    def test_create_pk_field(self):
        f = Field("id", Int64(), pk=True, nullable=False)
        assert f.pk is True
        assert f.nullable is False

    def test_field_to_dict(self):
        f = Field("id", Int64(min=1), pk=True, nullable=False, description="Primary key")
        d = f.to_dict()
        assert d["type"] == "Int64"
        assert d["min"] == 1
        assert d["nullable"] is False
        assert d["pk"] is True
        assert d["description"] == "Primary key"

    def test_field_to_dict_omits_false_pk(self):
        f = Field("name", String())
        d = f.to_dict()
        assert "pk" not in d

    def test_field_to_dict_omits_none_description(self):
        f = Field("x", Boolean())
        d = f.to_dict()
        assert "description" not in d

    def test_field_from_dict(self):
        d = {"type": "Int64", "min": 0, "nullable": False, "pk": True, "description": "id col"}
        f = Field.from_dict("my_id", d)
        assert f.name == "my_id"
        assert isinstance(f.type, Int64)
        assert f.nullable is False
        assert f.pk is True

    def test_field_from_dict_defaults(self):
        f = Field.from_dict("col", {"type": "String"})
        assert f.nullable is True
        assert f.pk is False
        assert f.description is None

    def test_field_from_dict_enum(self):
        d = {"type": "Enum", "allowed_values": ["A", "B"], "nullable": False}
        f = Field.from_dict("status", d)
        assert isinstance(f.type, Enum)
        assert f.type.allowed_values == ["A", "B"]

    def test_field_equality(self):
        f1 = Field("x", Int64(), nullable=False)
        f2 = Field("x", Int64(), nullable=False)
        assert f1 == f2

    def test_field_inequality_different_type(self):
        f1 = Field("x", Int64())
        f2 = Field("x", Float64())
        assert f1 != f2

    def test_field_inequality_different_nullable(self):
        f1 = Field("x", Int64(), nullable=True)
        f2 = Field("x", Int64(), nullable=False)
        assert f1 != f2


class TestDataContract:
    def test_create_contract(self, simple_contract):
        assert simple_contract.name == "transactions"
        assert simple_contract.version == "1.0.0"
        assert len(simple_contract.schema) == 6

    def test_default_breaking_changes(self):
        c = DataContract(name="x", version="1.0.0", schema={})
        assert c.breaking_changes == "FAIL"

    def test_default_expectations(self):
        c = DataContract(name="x", version="1.0.0", schema={})
        assert c.expectations == []

    def test_get_field_found(self, simple_contract):
        f = simple_contract.get_field("amount")
        assert f.name == "amount"

    def test_get_field_not_found(self, simple_contract):
        with pytest.raises(KeyError, match="not found"):
            simple_contract.get_field("nonexistent")

    def test_to_dict_keys(self, simple_contract):
        d = simple_contract.to_dict()
        assert "name" in d
        assert "version" in d
        assert "schema" in d
        assert "expectations" in d
        assert "breaking_changes" in d

    def test_to_dict_owner_included_when_set(self, simple_contract):
        d = simple_contract.to_dict()
        assert d["owner"] == "data-eng@example.com"

    def test_to_dict_omits_none_owner(self):
        c = DataContract(name="x", version="1.0.0", schema={})
        d = c.to_dict()
        assert "owner" not in d

    def test_from_dict_roundtrip(self, simple_contract):
        d = simple_contract.to_dict()
        restored = DataContract.from_dict(d)
        assert restored.name == simple_contract.name
        assert restored.version == simple_contract.version
        assert list(restored.schema) == list(simple_contract.schema)
        assert restored.expectations == simple_contract.expectations
        assert restored.breaking_changes == simple_contract.breaking_changes

    def test_from_dict_schema_types_preserved(self, simple_contract):
        d = simple_contract.to_dict()
        restored = DataContract.from_dict(d)
        assert isinstance(restored.schema["transaction_id"].type, Int64)
        assert isinstance(restored.schema["amount"].type, Float64)
        assert isinstance(restored.schema["status"].type, Enum)

    def test_equality(self, simple_contract):
        d = simple_contract.to_dict()
        assert DataContract.from_dict(d) == simple_contract

    def test_inequality_different_version(self, simple_contract):
        other = DataContract.from_dict({**simple_contract.to_dict(), "version": "2.0.0"})
        assert other != simple_contract

    def test_to_yaml_roundtrip(self, simple_contract):
        import yaml

        yaml_str = simple_contract.to_yaml()
        raw = yaml.safe_load(yaml_str)
        restored = DataContract.from_dict(raw)
        assert restored == simple_contract

    def test_to_json_roundtrip(self, simple_contract):
        import json

        json_str = simple_contract.to_json()
        raw = json.loads(json_str)
        restored = DataContract.from_dict(raw)
        assert restored == simple_contract

    def test_evolve_version(self, simple_contract):
        v2 = simple_contract.evolve(version="2.0.0")
        assert v2.version == "2.0.0"
        assert v2.name == simple_contract.name

    def test_evolve_schema_additions(self, simple_contract):
        v2 = simple_contract.evolve(
            version="1.1.0",
            schema_additions={"currency": Field("currency", String())},
        )
        assert "currency" in v2.schema
        assert "transaction_id" in v2.schema

    def test_evolve_schema_updates(self, simple_contract):
        new_amount = Field("amount", Float64(min=1.0, max=1_000_000), nullable=False)
        v2 = simple_contract.evolve(version="1.1.0", schema_updates={"amount": new_amount})
        assert v2.schema["amount"].type.min == 1.0

    def test_evolve_does_not_mutate_original(self, simple_contract):
        original_schema_len = len(simple_contract.schema)
        simple_contract.evolve(
            version="1.1.0",
            schema_additions={"new_col": Field("new_col", String())},
        )
        assert len(simple_contract.schema) == original_schema_len

    def test_repr(self, simple_contract):
        r = repr(simple_contract)
        assert "transactions" in r
        assert "1.0.0" in r

    def test_empty_contract(self, empty_contract):
        d = empty_contract.to_dict()
        restored = DataContract.from_dict(d)
        assert restored.name == "empty"
        assert restored.schema == {}

    def test_tags_roundtrip(self):
        c = DataContract(
            name="x",
            version="1.0.0",
            schema={},
            tags={"pii": "true", "team": "data-eng"},
        )
        restored = DataContract.from_dict(c.to_dict())
        assert restored.tags == {"pii": "true", "team": "data-eng"}
