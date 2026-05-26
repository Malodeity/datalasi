"""Integration tests for the PyArrow adapter."""

import pytest

pytest.importorskip("pyarrow")

import pyarrow as pa  # noqa: E402

from datalasi import Boolean, DataContract, Enum, Field, Float64, Int64, String  # noqa: E402
from datalasi.adapters.arrow_adapter import ArrowAdapter  # noqa: E402
from datalasi.core.types import Int32  # noqa: E402


@pytest.fixture
def contract():
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
def valid_table():
    return pa.table(
        {
            "id": pa.array([1, 2, 3], type=pa.int64()),
            "amount": pa.array([10.5, 20.0, 15.5], type=pa.float64()),
            "status": pa.array(["PENDING", "COMPLETED", "FAILED"]),
            "note": pa.array(["first", None, "third"]),
        }
    )


class TestValidateSuccess:
    def test_all_valid(self, contract, valid_table):
        result = ArrowAdapter.validate(valid_table, contract)
        assert result.success is True

    def test_row_count_metadata(self, contract, valid_table):
        result = ArrowAdapter.validate(valid_table, contract)
        assert result.metadata["row_count"] == 3

    def test_column_count_metadata(self, contract, valid_table):
        result = ArrowAdapter.validate(valid_table, contract)
        assert result.metadata["column_count"] == 4

    def test_via_contract_validate(self, contract, valid_table):
        result = contract.validate(valid_table)
        assert result.success is True


class TestMissingColumn:
    def test_missing_column_detected(self, contract):
        table = pa.table({"id": [1, 2], "amount": [5.0, 10.0]})
        result = ArrowAdapter.validate(table, contract)
        assert result.success is False
        types = [v.violation_type for v in result.schema_violations]
        assert "MISSING_COLUMN" in types


class TestTypeMismatch:
    def test_string_where_int_expected(self):
        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"id": Field("id", Int64(), nullable=False)},
        )
        table = pa.table({"id": pa.array(["a", "b", "c"])})
        result = ArrowAdapter.validate(table, contract)
        assert result.success is False
        assert any(v.violation_type == "TYPE_MISMATCH" for v in result.schema_violations)


class TestNullabilityViolation:
    def test_null_in_non_nullable_column(self, contract):
        table = pa.table(
            {
                "id": pa.array([1, None, 3], type=pa.int64()),
                "amount": pa.array([5.0, 10.0, 15.0]),
                "status": pa.array(["PENDING", "COMPLETED", "FAILED"]),
                "note": pa.array([None, None, None]),
            }
        )
        result = ArrowAdapter.validate(table, contract)
        assert result.success is False
        null_violations = [
            v for v in result.schema_violations if v.violation_type == "NULLABILITY_VIOLATION"
        ]
        assert any(v.column == "id" for v in null_violations)


class TestUnknownColumn:
    def test_unknown_column_is_warning(self, contract):
        table = pa.table(
            {
                "id": pa.array([1], type=pa.int64()),
                "amount": pa.array([5.0]),
                "status": pa.array(["PENDING"]),
                "note": pa.array([None]),
                "extra": pa.array(["unexpected"]),
            }
        )
        result = ArrowAdapter.validate(table, contract)
        unknowns = [v for v in result.schema_violations if v.violation_type == "UNKNOWN_COLUMN"]
        assert len(unknowns) == 1
        assert unknowns[0].severity == "WARNING"
        assert result.success is True


class TestInferSchema:
    def test_infer_int64(self):
        table = pa.table({"id": pa.array([1, 2, 3], type=pa.int64())})
        schema = ArrowAdapter.infer_schema(table)
        assert isinstance(schema["id"].type, Int64)

    def test_infer_int32(self):
        table = pa.table({"x": pa.array([1, 2, 3], type=pa.int32())})
        schema = ArrowAdapter.infer_schema(table)
        assert isinstance(schema["x"].type, Int32)

    def test_infer_float64(self):
        table = pa.table({"x": pa.array([1.0, 2.0], type=pa.float64())})
        schema = ArrowAdapter.infer_schema(table)
        assert isinstance(schema["x"].type, Float64)

    def test_infer_boolean(self):
        table = pa.table({"flag": pa.array([True, False])})
        schema = ArrowAdapter.infer_schema(table)
        assert isinstance(schema["flag"].type, Boolean)

    def test_infer_nullable(self):
        table = pa.table(
            {
                "a": pa.array([1, None, 3], type=pa.int64()),
                "b": pa.array([1, 2, 3], type=pa.int64()),
            }
        )
        schema = ArrowAdapter.infer_schema(table)
        assert schema["a"].nullable is True
        assert schema["b"].nullable is False

    def test_infer_string(self):
        table = pa.table({"name": pa.array(["Alice", "Bob"])})
        schema = ArrowAdapter.infer_schema(table)
        assert isinstance(schema["name"].type, String)
