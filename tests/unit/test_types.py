"""Unit tests for datalasi.core.types."""

import pytest

from datalasi.core.types import (
    Boolean,
    Date,
    Enum,
    Float64,
    Int32,
    Int64,
    String,
    Timestamp,
    type_from_dict,
)
from datalasi.errors import TypeValidationError


# ---------------------------------------------------------------------------
# Int64
# ---------------------------------------------------------------------------


class TestInt64:
    def test_validate_valid_int(self):
        assert Int64().validate(42) is True

    def test_validate_valid_float_whole(self):
        assert Int64().validate(3.0) is True

    def test_validate_none(self):
        assert Int64().validate(None) is True

    def test_validate_bool_rejected(self):
        assert Int64().validate(True) is False

    def test_validate_string_rejected(self):
        assert Int64().validate("hello") is False

    def test_validate_min(self):
        t = Int64(min=10)
        assert t.validate(10) is True
        assert t.validate(9) is False

    def test_validate_max(self):
        t = Int64(max=100)
        assert t.validate(100) is True
        assert t.validate(101) is False

    def test_validate_range(self):
        t = Int64(min=0, max=100)
        assert t.validate(50) is True
        assert t.validate(-1) is False
        assert t.validate(101) is False

    def test_coerce_int(self):
        assert Int64().coerce(42) == 42

    def test_coerce_string(self):
        assert Int64().coerce("99") == 99

    def test_coerce_float(self):
        assert Int64().coerce(3.9) == 3

    def test_coerce_none(self):
        assert Int64().coerce(None) is None

    def test_coerce_bool_raises(self):
        with pytest.raises(TypeValidationError):
            Int64().coerce(True)

    def test_coerce_invalid_raises(self):
        with pytest.raises(TypeValidationError):
            Int64().coerce("abc")

    def test_to_dict(self):
        assert Int64(min=0, max=10).to_dict() == {"type": "Int64", "min": 0, "max": 10}

    def test_to_dict_no_constraints(self):
        assert Int64().to_dict() == {"type": "Int64"}

    def test_from_dict_roundtrip(self):
        original = Int64(min=5, max=50)
        restored = Int64.from_dict(original.to_dict())
        assert restored.min == 5
        assert restored.max == 50

    def test_equality(self):
        assert Int64(min=1) == Int64(min=1)
        assert Int64(min=1) != Int64(min=2)


# ---------------------------------------------------------------------------
# Int32
# ---------------------------------------------------------------------------


class TestInt32:
    def test_validate_in_range(self):
        assert Int32().validate(2_147_483_647) is True
        assert Int32().validate(-2_147_483_648) is True

    def test_validate_out_of_range(self):
        assert Int32().validate(2_147_483_648) is False

    def test_coerce_out_of_range_raises(self):
        with pytest.raises(TypeValidationError):
            Int32().coerce(9_999_999_999)

    def test_roundtrip(self):
        t = Int32(min=0, max=255)
        assert Int32.from_dict(t.to_dict()).min == 0
        assert Int32.from_dict(t.to_dict()).max == 255


# ---------------------------------------------------------------------------
# Float64
# ---------------------------------------------------------------------------


class TestFloat64:
    def test_validate_float(self):
        assert Float64().validate(3.14) is True

    def test_validate_int_as_float(self):
        assert Float64().validate(5) is True

    def test_validate_none(self):
        assert Float64().validate(None) is True

    def test_validate_bool_rejected(self):
        assert Float64().validate(False) is False

    def test_validate_min(self):
        t = Float64(min=0.01)
        assert t.validate(0.01) is True
        assert t.validate(0.009) is False

    def test_validate_max(self):
        t = Float64(max=1.0)
        assert t.validate(1.0) is True
        assert t.validate(1.001) is False

    def test_coerce_string(self):
        assert Float64().coerce("1.5") == 1.5

    def test_coerce_none(self):
        assert Float64().coerce(None) is None

    def test_coerce_bool_raises(self):
        with pytest.raises(TypeValidationError):
            Float64().coerce(True)

    def test_to_dict_roundtrip(self):
        t = Float64(min=0.01, max=999.99)
        assert Float64.from_dict(t.to_dict()).min == pytest.approx(0.01)
        assert Float64.from_dict(t.to_dict()).max == pytest.approx(999.99)


# ---------------------------------------------------------------------------
# String
# ---------------------------------------------------------------------------


class TestString:
    def test_validate_string(self):
        assert String().validate("hello") is True

    def test_validate_none(self):
        assert String().validate(None) is True

    def test_validate_non_string_rejected(self):
        assert String().validate(42) is False

    def test_validate_max_length(self):
        t = String(max_length=5)
        assert t.validate("hello") is True
        assert t.validate("toolong") is False

    def test_validate_pattern(self):
        t = String(pattern=r"\d{3}-\d{4}")
        assert t.validate("123-4567") is True
        assert t.validate("abc-defg") is False

    def test_coerce_int_to_string(self):
        assert String().coerce(99) == "99"

    def test_coerce_none(self):
        assert String().coerce(None) is None

    def test_coerce_exceeds_max_length_raises(self):
        with pytest.raises(TypeValidationError):
            String(max_length=3).coerce("toolong")

    def test_to_dict_roundtrip(self):
        t = String(max_length=100, pattern=r"[a-z]+")
        restored = String.from_dict(t.to_dict())
        assert restored.max_length == 100
        assert restored.pattern == r"[a-z]+"

    def test_to_dict_no_constraints(self):
        assert String().to_dict() == {"type": "String"}


# ---------------------------------------------------------------------------
# Boolean
# ---------------------------------------------------------------------------


class TestBoolean:
    def test_validate_true(self):
        assert Boolean().validate(True) is True

    def test_validate_false(self):
        assert Boolean().validate(False) is True

    def test_validate_none(self):
        assert Boolean().validate(None) is True

    def test_validate_int_rejected(self):
        assert Boolean().validate(1) is False

    def test_coerce_string_true(self):
        assert Boolean().coerce("true") is True

    def test_coerce_string_false(self):
        assert Boolean().coerce("false") is False

    def test_coerce_int_zero(self):
        assert Boolean().coerce(0) is False

    def test_coerce_int_one(self):
        assert Boolean().coerce(1) is True

    def test_coerce_invalid_raises(self):
        with pytest.raises(TypeValidationError):
            Boolean().coerce("maybe")

    def test_coerce_none(self):
        assert Boolean().coerce(None) is None

    def test_roundtrip(self):
        t = Boolean()
        assert Boolean.from_dict(t.to_dict()).name == "Boolean"


# ---------------------------------------------------------------------------
# Date
# ---------------------------------------------------------------------------


class TestDate:
    def test_validate_valid(self):
        assert Date().validate("2024-01-15") is True

    def test_validate_none(self):
        assert Date().validate(None) is True

    def test_validate_invalid_format(self):
        assert Date().validate("15-01-2024") is False
        assert Date().validate("2024/01/15") is False

    def test_validate_non_string(self):
        assert Date().validate(20240115) is False

    def test_coerce_valid(self):
        assert Date().coerce("2024-01-15") == "2024-01-15"

    def test_coerce_invalid_raises(self):
        with pytest.raises(TypeValidationError):
            Date().coerce("not-a-date")

    def test_coerce_none(self):
        assert Date().coerce(None) is None

    def test_roundtrip(self):
        t = Date()
        assert Date.from_dict(t.to_dict()).name == "Date"


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------


class TestTimestamp:
    def test_validate_string(self):
        assert Timestamp().validate("2024-01-15T12:00:00Z") is True

    def test_validate_none(self):
        assert Timestamp().validate(None) is True

    def test_validate_non_string(self):
        assert Timestamp().validate(12345) is False

    def test_coerce_string(self):
        assert Timestamp().coerce("2024-01-15T00:00:00") == "2024-01-15T00:00:00"

    def test_coerce_none(self):
        assert Timestamp().coerce(None) is None

    def test_coerce_non_string_raises(self):
        with pytest.raises(TypeValidationError):
            Timestamp().coerce(123)

    def test_to_dict_with_timezone(self):
        t = Timestamp(timezone="UTC")
        d = t.to_dict()
        assert d["timezone"] == "UTC"

    def test_roundtrip(self):
        t = Timestamp(timezone="UTC")
        restored = Timestamp.from_dict(t.to_dict())
        assert restored.timezone == "UTC"


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class TestEnum:
    def test_validate_allowed(self):
        t = Enum(["A", "B", "C"])
        assert t.validate("A") is True
        assert t.validate("B") is True

    def test_validate_disallowed(self):
        t = Enum(["A", "B", "C"])
        assert t.validate("D") is False

    def test_validate_none(self):
        assert Enum(["A"]).validate(None) is True

    def test_validate_case_sensitive(self):
        t = Enum(["PENDING"])
        assert t.validate("pending") is False

    def test_coerce_valid(self):
        t = Enum(["OK", "FAIL"])
        assert t.coerce("OK") == "OK"

    def test_coerce_none(self):
        assert Enum(["X"]).coerce(None) is None

    def test_coerce_invalid_raises(self):
        with pytest.raises(TypeValidationError):
            Enum(["A", "B"]).coerce("C")

    def test_empty_allowed_values_raises(self):
        with pytest.raises(ValueError):
            Enum([])

    def test_roundtrip(self):
        t = Enum(["PENDING", "COMPLETED", "FAILED"])
        restored = Enum.from_dict(t.to_dict())
        assert restored.allowed_values == ["PENDING", "COMPLETED", "FAILED"]

    def test_equality(self):
        assert Enum(["A", "B"]) == Enum(["A", "B"])
        assert Enum(["A"]) != Enum(["B"])


# ---------------------------------------------------------------------------
# type_from_dict registry
# ---------------------------------------------------------------------------


class TestTypeFromDict:
    def test_int64(self):
        t = type_from_dict({"type": "Int64", "min": 0})
        assert isinstance(t, Int64)
        assert t.min == 0

    def test_float64(self):
        t = type_from_dict({"type": "Float64", "max": 100.0})
        assert isinstance(t, Float64)
        assert t.max == 100.0

    def test_string(self):
        t = type_from_dict({"type": "String", "max_length": 50})
        assert isinstance(t, String)

    def test_enum(self):
        t = type_from_dict({"type": "Enum", "allowed_values": ["X", "Y"]})
        assert isinstance(t, Enum)
        assert t.allowed_values == ["X", "Y"]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown type"):
            type_from_dict({"type": "UnsupportedType"})
