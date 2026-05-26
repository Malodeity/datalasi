"""Integration tests for the Polars adapter."""

import pytest

pytest.importorskip("polars")

import polars as pl  # noqa: E402

from datalasi import Boolean, DataContract, Enum, Field, Float64, Int64, String
from datalasi.adapters.polars_adapter import PolarsAdapter
from datalasi.core.types import Int32

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def transactions_contract():
    return DataContract(
        name="transactions",
        version="1.0.0",
        schema={
            "id": Field("id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01), nullable=False),
            "status": Field("status", Enum(["PENDING", "COMPLETED", "FAILED"]), nullable=False),
            "note": Field("note", String()),
        },
        expectations=["amount > 0"],
    )


@pytest.fixture
def valid_df():
    return pl.DataFrame(
        {
            "id": [1, 2, 3],
            "amount": [10.5, 20.0, 15.5],
            "status": ["PENDING", "COMPLETED", "FAILED"],
            "note": ["first", None, "third"],
        }
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestValidateSuccess:
    def test_all_valid(self, transactions_contract, valid_df):
        result = PolarsAdapter.validate(valid_df, transactions_contract)
        assert result.success is True

    def test_metadata_row_count(self, transactions_contract, valid_df):
        result = PolarsAdapter.validate(valid_df, transactions_contract)
        assert result.metadata["row_count"] == 3

    def test_metadata_column_count(self, transactions_contract, valid_df):
        result = PolarsAdapter.validate(valid_df, transactions_contract)
        assert result.metadata["column_count"] == 4

    def test_via_contract_validate(self, transactions_contract, valid_df):
        result = transactions_contract.validate(valid_df)
        assert result.success is True


# ---------------------------------------------------------------------------
# Schema violations
# ---------------------------------------------------------------------------


class TestMissingColumn:
    def test_missing_column_detected(self, transactions_contract):
        df = pl.DataFrame({"id": [1, 2], "amount": [5.0, 10.0]})
        result = PolarsAdapter.validate(df, transactions_contract)
        assert result.success is False
        types = [v.violation_type for v in result.schema_violations]
        assert "MISSING_COLUMN" in types

    def test_missing_column_names_recorded(self, transactions_contract):
        df = pl.DataFrame({"id": [1]})
        result = PolarsAdapter.validate(df, transactions_contract)
        missing = [
            v.column for v in result.schema_violations if v.violation_type == "MISSING_COLUMN"
        ]
        assert "amount" in missing
        assert "status" in missing


class TestTypeMismatch:
    def test_string_where_int_expected(self):
        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"id": Field("id", Int64(), nullable=False)},
        )
        df = pl.DataFrame({"id": ["a", "b", "c"]})
        result = PolarsAdapter.validate(df, contract)
        assert result.success is False
        assert any(v.violation_type == "TYPE_MISMATCH" for v in result.schema_violations)


class TestNullabilityViolation:
    def test_null_in_non_nullable_column(self, transactions_contract):
        df = pl.DataFrame(
            {
                "id": [1, None, 3],
                "amount": [5.0, 10.0, 15.0],
                "status": ["PENDING", "COMPLETED", "FAILED"],
                "note": [None, None, None],
            }
        )
        result = PolarsAdapter.validate(df, transactions_contract)
        assert result.success is False
        null_violations = [
            v for v in result.schema_violations if v.violation_type == "NULLABILITY_VIOLATION"
        ]
        assert any(v.column == "id" for v in null_violations)

    def test_null_in_nullable_column_ok(self, transactions_contract, valid_df):
        result = PolarsAdapter.validate(valid_df, transactions_contract)
        null_violations = [
            v for v in result.schema_violations if v.violation_type == "NULLABILITY_VIOLATION"
        ]
        assert all(v.column != "note" for v in null_violations)


class TestUnknownColumn:
    def test_unknown_column_is_warning(self, transactions_contract):
        df = pl.DataFrame(
            {
                "id": [1],
                "amount": [5.0],
                "status": ["PENDING"],
                "note": [None],
                "extra": ["unexpected"],
            }
        )
        result = PolarsAdapter.validate(df, transactions_contract)
        unknowns = [v for v in result.schema_violations if v.violation_type == "UNKNOWN_COLUMN"]
        assert len(unknowns) == 1
        assert unknowns[0].severity == "WARNING"

    def test_unknown_column_does_not_fail(self, transactions_contract):
        df = pl.DataFrame(
            {
                "id": [1],
                "amount": [5.0],
                "status": ["PENDING"],
                "note": [None],
                "extra": ["x"],
            }
        )
        result = PolarsAdapter.validate(df, transactions_contract)
        assert result.success is True


# ---------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------


class TestExpectations:
    def test_expectation_failure(self):
        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"amount": Field("amount", Float64())},
            expectations=["amount > 0"],
        )
        df = pl.DataFrame({"amount": [10.0, -5.0, 20.0]})
        result = PolarsAdapter.validate(df, contract)
        assert result.success is False
        assert len(result.expectation_violations) == 1
        assert result.expectation_violations[0].row_count == 1

    def test_expectation_all_pass(self):
        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"amount": Field("amount", Float64())},
            expectations=["amount > 0"],
        )
        df = pl.DataFrame({"amount": [1.0, 2.0, 3.0]})
        result = PolarsAdapter.validate(df, contract)
        assert result.expectation_violations == []

    def test_invalid_expectation_recorded(self):
        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"x": Field("x", Int64())},
            expectations=["nonexistent_col > 0"],
        )
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = PolarsAdapter.validate(df, contract)
        assert result.success is False
        assert result.expectation_violations[0].description is not None


# ---------------------------------------------------------------------------
# infer_schema
# ---------------------------------------------------------------------------


class TestInferSchema:
    def test_infer_int64(self):
        df = pl.DataFrame({"id": pl.Series([1, 2, 3], dtype=pl.Int64)})
        schema = PolarsAdapter.infer_schema(df)
        assert isinstance(schema["id"].type, Int64)

    def test_infer_int32(self):
        df = pl.DataFrame({"x": pl.Series([1, 2, 3], dtype=pl.Int32)})
        schema = PolarsAdapter.infer_schema(df)
        assert isinstance(schema["x"].type, Int32)

    def test_infer_float64(self):
        df = pl.DataFrame({"x": pl.Series([1.0, 2.0], dtype=pl.Float64)})
        schema = PolarsAdapter.infer_schema(df)
        assert isinstance(schema["x"].type, Float64)

    def test_infer_boolean(self):
        df = pl.DataFrame({"flag": [True, False, True]})
        schema = PolarsAdapter.infer_schema(df)
        assert isinstance(schema["flag"].type, Boolean)

    def test_infer_nullable(self):
        df = pl.DataFrame({"a": [1, None, 3], "b": [1, 2, 3]})
        schema = PolarsAdapter.infer_schema(df)
        assert schema["a"].nullable is True
        assert schema["b"].nullable is False

    def test_infer_string(self):
        df = pl.DataFrame({"name": ["Alice", "Bob"]})
        schema = PolarsAdapter.infer_schema(df)
        assert isinstance(schema["name"].type, String)

    def test_infer_columns_preserved(self):
        df = pl.DataFrame({"x": [1], "y": [2.0], "z": ["a"]})
        schema = PolarsAdapter.infer_schema(df)
        assert set(schema.keys()) == {"x", "y", "z"}
