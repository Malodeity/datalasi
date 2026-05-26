"""Integration tests for the Pandas adapter."""

import pytest

pd = pytest.importorskip("pandas")

import pandas as pd  # noqa: E402 — only reached if pandas is installed

from datalasi import DataContract, Field, Float64, Int64, String, Enum, Boolean, Timestamp
from datalasi.adapters.pandas_adapter import PandasAdapter


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
            "note": Field("note", String(max_length=200)),
        },
        expectations=["amount > 0"],
    )


@pytest.fixture
def valid_df():
    return pd.DataFrame(
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
        result = PandasAdapter.validate(valid_df, transactions_contract)
        assert result.success is True
        assert result.schema_violations == [] or all(
            v.severity == "WARNING" for v in result.schema_violations
        )

    def test_metadata_row_count(self, transactions_contract, valid_df):
        result = PandasAdapter.validate(valid_df, transactions_contract)
        assert result.metadata["row_count"] == 3

    def test_metadata_column_count(self, transactions_contract, valid_df):
        result = PandasAdapter.validate(valid_df, transactions_contract)
        assert result.metadata["column_count"] == 4

    def test_metadata_null_counts(self, transactions_contract, valid_df):
        result = PandasAdapter.validate(valid_df, transactions_contract)
        assert result.metadata["null_counts"]["note"] == 1
        assert result.metadata["null_counts"]["id"] == 0

    def test_via_contract_validate(self, transactions_contract, valid_df):
        result = transactions_contract.validate(valid_df)
        assert result.success is True


# ---------------------------------------------------------------------------
# Schema violations
# ---------------------------------------------------------------------------


class TestMissingColumn:
    def test_missing_column_detected(self, transactions_contract):
        df = pd.DataFrame({"id": [1, 2], "amount": [5.0, 10.0]})
        result = PandasAdapter.validate(df, transactions_contract)
        assert result.success is False
        types = [v.violation_type for v in result.schema_violations]
        assert "MISSING_COLUMN" in types

    def test_missing_column_name_recorded(self, transactions_contract):
        df = pd.DataFrame({"id": [1]})
        result = PandasAdapter.validate(df, transactions_contract)
        missing = [v.column for v in result.schema_violations if v.violation_type == "MISSING_COLUMN"]
        assert "amount" in missing
        assert "status" in missing


class TestTypeMismatch:
    def test_string_where_int_expected(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"id": Field("id", Int64(), nullable=False)},
        )
        df = pd.DataFrame({"id": ["a", "b", "c"]})
        result = PandasAdapter.validate(df, contract)
        assert result.success is False
        assert any(v.violation_type == "TYPE_MISMATCH" for v in result.schema_violations)

    def test_float_where_bool_expected(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"flag": Field("flag", Boolean())},
        )
        df = pd.DataFrame({"flag": [1.0, 0.0, 1.0]})
        result = PandasAdapter.validate(df, contract)
        assert result.success is False


class TestNullabilityViolation:
    def test_null_in_non_nullable_column(self, transactions_contract):
        df = pd.DataFrame(
            {
                "id": [1, None, 3],
                "amount": [5.0, 10.0, 15.0],
                "status": ["PENDING", "COMPLETED", "FAILED"],
                "note": [None, None, None],
            }
        )
        result = PandasAdapter.validate(df, transactions_contract)
        assert result.success is False
        null_violations = [
            v for v in result.schema_violations if v.violation_type == "NULLABILITY_VIOLATION"
        ]
        assert any(v.column == "id" for v in null_violations)

    def test_null_in_nullable_column_ok(self, transactions_contract, valid_df):
        result = PandasAdapter.validate(valid_df, transactions_contract)
        null_violations = [
            v for v in result.schema_violations if v.violation_type == "NULLABILITY_VIOLATION"
        ]
        assert all(v.column != "note" for v in null_violations)


class TestUnknownColumn:
    def test_unknown_column_is_warning(self, transactions_contract):
        df = pd.DataFrame(
            {
                "id": [1],
                "amount": [5.0],
                "status": ["PENDING"],
                "note": [None],
                "extra_col": ["unexpected"],
            }
        )
        result = PandasAdapter.validate(df, transactions_contract)
        unknowns = [v for v in result.schema_violations if v.violation_type == "UNKNOWN_COLUMN"]
        assert len(unknowns) == 1
        assert unknowns[0].column == "extra_col"
        assert unknowns[0].severity == "WARNING"

    def test_unknown_column_does_not_fail_result(self, transactions_contract):
        df = pd.DataFrame(
            {
                "id": [1],
                "amount": [5.0],
                "status": ["PENDING"],
                "note": [None],
                "extra_col": ["x"],
            }
        )
        result = PandasAdapter.validate(df, transactions_contract)
        assert result.success is True


class TestEnumViolation:
    def test_invalid_enum_value(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"status": Field("status", Enum(["A", "B"]), nullable=False)},
        )
        df = pd.DataFrame({"status": ["A", "C", "B"]})
        result = PandasAdapter.validate(df, contract)
        assert result.success is False

    def test_valid_enum_values_pass(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"status": Field("status", Enum(["A", "B"]))},
        )
        df = pd.DataFrame({"status": ["A", "B", "A"]})
        result = PandasAdapter.validate(df, contract)
        error_violations = [v for v in result.schema_violations if v.severity == "ERROR"]
        assert len(error_violations) == 0


# ---------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------


class TestExpectations:
    def test_expectation_amount_gt_zero(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"amount": Field("amount", Float64())},
            expectations=["amount > 0"],
        )
        df = pd.DataFrame({"amount": [10.0, -5.0, 20.0]})
        result = PandasAdapter.validate(df, contract)
        assert result.success is False
        assert len(result.expectation_violations) == 1
        assert result.expectation_violations[0].row_count == 1

    def test_expectation_all_pass(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"amount": Field("amount", Float64())},
            expectations=["amount > 0"],
        )
        df = pd.DataFrame({"amount": [1.0, 2.0, 3.0]})
        result = PandasAdapter.validate(df, contract)
        assert result.expectation_violations == []

    def test_expectation_multiple_rules(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={
                "amount": Field("amount", Float64()),
                "qty": Field("qty", Int64()),
            },
            expectations=["amount > 0", "qty > 0"],
        )
        df = pd.DataFrame({"amount": [-1.0, 5.0], "qty": [2, -3]})
        result = PandasAdapter.validate(df, contract)
        assert len(result.expectation_violations) == 2

    def test_expectation_row_indices_captured(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"x": Field("x", Int64())},
            expectations=["x > 10"],
        )
        df = pd.DataFrame({"x": [5, 15, 3, 20]})
        result = PandasAdapter.validate(df, contract)
        assert result.expectation_violations[0].row_count == 2

    def test_invalid_expectation_recorded(self):
        contract = DataContract(
            name="t", version="1.0.0",
            schema={"x": Field("x", Int64())},
            expectations=["nonexistent_col > 0"],
        )
        df = pd.DataFrame({"x": [1, 2, 3]})
        result = PandasAdapter.validate(df, contract)
        assert result.success is False
        assert result.expectation_violations[0].description is not None


# ---------------------------------------------------------------------------
# infer_schema
# ---------------------------------------------------------------------------


class TestInferSchema:
    def test_infer_basic_types(self):
        df = pd.DataFrame(
            {
                "id": pd.array([1, 2, 3], dtype="int64"),
                "score": [1.5, 2.5, 3.5],
                "name": ["a", "b", "c"],
                "active": [True, False, True],
            }
        )
        schema = PandasAdapter.infer_schema(df)
        assert isinstance(schema["id"].type, Int64)
        assert isinstance(schema["score"].type, Float64)
        assert isinstance(schema["name"].type, String)
        assert isinstance(schema["active"].type, Boolean)

    def test_infer_nullable(self):
        df = pd.DataFrame(
            {
                "a": [1, None, 3],
                "b": [1, 2, 3],
            }
        )
        schema = PandasAdapter.infer_schema(df)
        assert schema["a"].nullable is True
        assert schema["b"].nullable is False

    def test_infer_datetime(self):
        df = pd.DataFrame({"ts": pd.to_datetime(["2024-01-01", "2024-01-02"])})
        schema = PandasAdapter.infer_schema(df)
        assert isinstance(schema["ts"].type, Timestamp)

    def test_infer_schema_columns_preserved(self):
        df = pd.DataFrame({"x": [1], "y": [2], "z": [3]})
        schema = PandasAdapter.infer_schema(df)
        assert set(schema.keys()) == {"x", "y", "z"}
