"""Unit tests for dbt schema.yml export."""

from __future__ import annotations

import pytest

from datalasi import DataContract, Enum, Field, Float64, Int64, String
from datalasi.export.dbt import to_dbt_schema, to_dbt_schema_yaml


@pytest.fixture
def contract():
    return DataContract(
        name="transactions",
        version="1.0.0",
        description="Customer transactions",
        owner="eng@co.com",
        schema={
            "id": Field("id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01, max=1_000_000), nullable=False),
            "status": Field(
                "status",
                Enum(["PENDING", "COMPLETED", "FAILED"]),
                nullable=False,
                description="Transaction status",
            ),
            "note": Field("note", String(max_length=500)),
        },
    )


class TestStructure:
    def test_version_is_2(self, contract):
        schema = to_dbt_schema(contract)
        assert schema["version"] == 2

    def test_models_key(self, contract):
        schema = to_dbt_schema(contract)
        assert "models" in schema
        assert len(schema["models"]) == 1

    def test_model_name_defaults_to_contract_name(self, contract):
        schema = to_dbt_schema(contract)
        assert schema["models"][0]["name"] == "transactions"

    def test_model_name_override(self, contract):
        schema = to_dbt_schema(contract, model_name="stg_transactions")
        assert schema["models"][0]["name"] == "stg_transactions"

    def test_description_included(self, contract):
        schema = to_dbt_schema(contract)
        assert schema["models"][0]["description"] == "Customer transactions"

    def test_meta_contract_version(self, contract):
        schema = to_dbt_schema(contract)
        assert schema["models"][0]["meta"]["contract_version"] == "1.0.0"

    def test_meta_contract_owner(self, contract):
        schema = to_dbt_schema(contract)
        assert schema["models"][0]["meta"]["contract_owner"] == "eng@co.com"

    def test_columns_count(self, contract):
        schema = to_dbt_schema(contract)
        cols = schema["models"][0]["columns"]
        assert len(cols) == 4

    def test_column_names(self, contract):
        schema = to_dbt_schema(contract)
        names = [c["name"] for c in schema["models"][0]["columns"]]
        assert set(names) == {"id", "amount", "status", "note"}

    def test_column_description_included(self, contract):
        schema = to_dbt_schema(contract)
        status_col = next(c for c in schema["models"][0]["columns"] if c["name"] == "status")
        assert status_col["description"] == "Transaction status"


class TestTests:
    def _get_col(self, schema, name):
        return next(c for c in schema["models"][0]["columns"] if c["name"] == name)

    def test_not_null_for_non_nullable(self, contract):
        schema = to_dbt_schema(contract)
        id_col = self._get_col(schema, "id")
        assert "not_null" in id_col["tests"]

    def test_unique_for_pk(self, contract):
        schema = to_dbt_schema(contract)
        id_col = self._get_col(schema, "id")
        assert "unique" in id_col["tests"]

    def test_no_not_null_for_nullable(self, contract):
        schema = to_dbt_schema(contract)
        note_col = self._get_col(schema, "note")
        tests = note_col.get("tests", [])
        assert "not_null" not in tests

    def test_accepted_values_for_enum(self, contract):
        schema = to_dbt_schema(contract)
        status_col = self._get_col(schema, "status")
        av_tests = [
            t for t in status_col["tests"] if isinstance(t, dict) and "accepted_values" in t
        ]
        assert len(av_tests) == 1
        assert set(av_tests[0]["accepted_values"]["values"]) == {"PENDING", "COMPLETED", "FAILED"}

    def test_expression_is_true_for_min(self, contract):
        schema = to_dbt_schema(contract)
        amount_col = self._get_col(schema, "amount")
        expr_tests = [
            t
            for t in amount_col["tests"]
            if isinstance(t, dict) and "dbt_utils.expression_is_true" in t
        ]
        expressions = [t["dbt_utils.expression_is_true"]["expression"] for t in expr_tests]
        assert any(">= 0.01" in e for e in expressions)

    def test_expression_is_true_for_max(self, contract):
        schema = to_dbt_schema(contract)
        amount_col = self._get_col(schema, "amount")
        expr_tests = [
            t
            for t in amount_col["tests"]
            if isinstance(t, dict) and "dbt_utils.expression_is_true" in t
        ]
        expressions = [t["dbt_utils.expression_is_true"]["expression"] for t in expr_tests]
        assert any("<= 1000000" in e for e in expressions)

    def test_max_length_generates_test(self, contract):
        schema = to_dbt_schema(contract)
        note_col = self._get_col(schema, "note")
        expr_tests = [
            t
            for t in (note_col.get("tests") or [])
            if isinstance(t, dict) and "dbt_utils.expression_is_true" in t
        ]
        assert any("length" in t["dbt_utils.expression_is_true"]["expression"] for t in expr_tests)


class TestSourceBlock:
    def test_source_name_generates_sources_key(self, contract):
        schema = to_dbt_schema(contract, source_name="raw_postgres")
        assert "sources" in schema
        assert "models" not in schema

    def test_source_name_is_set(self, contract):
        schema = to_dbt_schema(contract, source_name="raw_postgres")
        assert schema["sources"][0]["name"] == "raw_postgres"

    def test_table_name_in_source(self, contract):
        schema = to_dbt_schema(contract, source_name="raw_postgres")
        tables = schema["sources"][0]["tables"]
        assert tables[0]["name"] == "transactions"


class TestYamlOutput:
    def test_yaml_is_string(self, contract):
        yaml_str = to_dbt_schema_yaml(contract)
        assert isinstance(yaml_str, str)

    def test_yaml_contains_version(self, contract):
        yaml_str = to_dbt_schema_yaml(contract)
        assert "version: 2" in yaml_str

    def test_yaml_contains_column_name(self, contract):
        yaml_str = to_dbt_schema_yaml(contract)
        assert "transactions" in yaml_str

    def test_convenience_method_on_contract(self, contract):
        assert contract.to_dbt_schema() == to_dbt_schema(contract)
        assert contract.to_dbt_schema_yaml() == to_dbt_schema_yaml(contract)
