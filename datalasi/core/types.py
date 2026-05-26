"""Type system for datalasi data contracts.

Each concrete type supports validate(), coerce(), to_dict(), and from_dict()
so contracts can be serialized to/from YAML without losing type information.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type


class DataType(ABC):
    """Abstract base for all contract field types."""

    name: str

    @abstractmethod
    def validate(self, value: Any) -> bool:
        """Return True if *value* conforms to this type, False otherwise.

        Never raises — returns False for invalid values instead.
        None is always considered valid here; nullability is enforced at the
        Field level.
        """

    @abstractmethod
    def coerce(self, value: Any) -> Any:
        """Convert *value* to the native Python type.

        Raises:
            TypeValidationError: if the value cannot be converted.
        """

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize this type to a plain dict suitable for YAML output."""

    @classmethod
    @abstractmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DataType":
        """Deserialize a type from a plain dict (e.g. loaded from YAML)."""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DataType):
            return NotImplemented
        return self.to_dict() == other.to_dict()


# ---------------------------------------------------------------------------
# Integer types
# ---------------------------------------------------------------------------


class Int64(DataType):
    """64-bit signed integer with optional min/max constraints."""

    name = "Int64"

    def __init__(self, min: Optional[int] = None, max: Optional[int] = None):
        self.min = min
        self.max = max

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return False
        try:
            int_val = int(value)
        except (TypeError, ValueError):
            return False
        if self.min is not None and int_val < self.min:
            return False
        if self.max is not None and int_val > self.max:
            return False
        return True

    def coerce(self, value: Any) -> Optional[int]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        if isinstance(value, bool):
            raise TypeValidationError(f"Cannot coerce bool {value!r} to Int64")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise TypeValidationError(f"Cannot coerce {value!r} to Int64: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.name}
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Int64":
        return cls(min=d.get("min"), max=d.get("max"))

    def __repr__(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f"min={self.min}")
        if self.max is not None:
            parts.append(f"max={self.max}")
        return f"Int64({', '.join(parts)})"


class Int32(DataType):
    """32-bit signed integer with optional min/max constraints."""

    name = "Int32"
    _RANGE = (-2_147_483_648, 2_147_483_647)

    def __init__(self, min: Optional[int] = None, max: Optional[int] = None):
        self.min = min
        self.max = max

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return False
        try:
            int_val = int(value)
        except (TypeError, ValueError):
            return False
        lo, hi = self._RANGE
        if not (lo <= int_val <= hi):
            return False
        if self.min is not None and int_val < self.min:
            return False
        if self.max is not None and int_val > self.max:
            return False
        return True

    def coerce(self, value: Any) -> Optional[int]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        if isinstance(value, bool):
            raise TypeValidationError(f"Cannot coerce bool {value!r} to Int32")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise TypeValidationError(f"Cannot coerce {value!r} to Int32: {exc}") from exc
        lo, hi = self._RANGE
        if not (lo <= result <= hi):
            raise TypeValidationError(f"Value {result} out of Int32 range [{lo}, {hi}]")
        return result

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.name}
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Int32":
        return cls(min=d.get("min"), max=d.get("max"))

    def __repr__(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f"min={self.min}")
        if self.max is not None:
            parts.append(f"max={self.max}")
        return f"Int32({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Floating-point types
# ---------------------------------------------------------------------------


class Float64(DataType):
    """64-bit floating-point number with optional min/max constraints."""

    name = "Float64"

    def __init__(self, min: Optional[float] = None, max: Optional[float] = None):
        self.min = min
        self.max = max

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return False
        try:
            f_val = float(value)
        except (TypeError, ValueError):
            return False
        if self.min is not None and f_val < self.min:
            return False
        if self.max is not None and f_val > self.max:
            return False
        return True

    def coerce(self, value: Any) -> Optional[float]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        if isinstance(value, bool):
            raise TypeValidationError(f"Cannot coerce bool {value!r} to Float64")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise TypeValidationError(f"Cannot coerce {value!r} to Float64: {exc}") from exc

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.name}
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Float64":
        return cls(min=d.get("min"), max=d.get("max"))

    def __repr__(self) -> str:
        parts = []
        if self.min is not None:
            parts.append(f"min={self.min}")
        if self.max is not None:
            parts.append(f"max={self.max}")
        return f"Float64({', '.join(parts)})"


# ---------------------------------------------------------------------------
# String type
# ---------------------------------------------------------------------------


class String(DataType):
    """Variable-length string with optional max_length and regex pattern."""

    name = "String"

    def __init__(
        self,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
    ):
        self.max_length = max_length
        self.pattern = pattern
        self._compiled: Optional[re.Pattern] = re.compile(pattern) if pattern else None

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        if self.max_length is not None and len(value) > self.max_length:
            return False
        if self._compiled is not None and not self._compiled.fullmatch(value):
            return False
        return True

    def coerce(self, value: Any) -> Optional[str]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        result = str(value)
        if self.max_length is not None and len(result) > self.max_length:
            raise TypeValidationError(
                f"String length {len(result)} exceeds max_length {self.max_length}"
            )
        if self._compiled is not None and not self._compiled.fullmatch(result):
            raise TypeValidationError(
                f"String {result!r} does not match pattern {self.pattern!r}"
            )
        return result

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.name}
        if self.max_length is not None:
            d["max_length"] = self.max_length
        if self.pattern is not None:
            d["pattern"] = self.pattern
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "String":
        return cls(max_length=d.get("max_length"), pattern=d.get("pattern"))

    def __repr__(self) -> str:
        parts = []
        if self.max_length is not None:
            parts.append(f"max_length={self.max_length}")
        if self.pattern is not None:
            parts.append(f"pattern={self.pattern!r}")
        return f"String({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Boolean type
# ---------------------------------------------------------------------------


class Boolean(DataType):
    """Boolean true/false type."""

    name = "Boolean"

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, bool)

    def coerce(self, value: Any) -> Optional[bool]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lower = value.lower()
            if lower in ("true", "1", "yes"):
                return True
            if lower in ("false", "0", "no"):
                return False
        raise TypeValidationError(f"Cannot coerce {value!r} to Boolean")

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.name}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Boolean":
        return cls()


# ---------------------------------------------------------------------------
# Date and Timestamp types (stored as strings in Phase 1)
# ---------------------------------------------------------------------------


class Date(DataType):
    """Calendar date, represented as a string in YYYY-MM-DD format."""

    name = "Date"
    _PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, str) and bool(self._PATTERN.match(value))

    def coerce(self, value: Any) -> Optional[str]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        s = str(value)
        if not self._PATTERN.match(s):
            raise TypeValidationError(
                f"Cannot coerce {value!r} to Date — expected YYYY-MM-DD format"
            )
        return s

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.name}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Date":
        return cls()


class Timestamp(DataType):
    """Date-time value with optional timezone label (stored as string in Phase 1)."""

    name = "Timestamp"

    def __init__(self, timezone: Optional[str] = None):
        self.timezone = timezone

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return isinstance(value, str) and len(value) > 0

    def coerce(self, value: Any) -> Optional[str]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeValidationError(
                f"Cannot coerce {value!r} to Timestamp — expected string"
            )
        return value

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.name}
        if self.timezone is not None:
            d["timezone"] = self.timezone
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Timestamp":
        return cls(timezone=d.get("timezone"))

    def __repr__(self) -> str:
        if self.timezone:
            return f"Timestamp(timezone={self.timezone!r})"
        return "Timestamp()"


# ---------------------------------------------------------------------------
# Enum type
# ---------------------------------------------------------------------------


class Enum(DataType):
    """Categorical type with a fixed set of allowed string values."""

    name = "Enum"

    def __init__(self, allowed_values: List[str]):
        if not allowed_values:
            raise ValueError("Enum requires at least one allowed value")
        self.allowed_values = list(allowed_values)

    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return value in self.allowed_values

    def coerce(self, value: Any) -> Optional[str]:
        from datalasi.errors import TypeValidationError

        if value is None:
            return None
        s = str(value)
        if s not in self.allowed_values:
            raise TypeValidationError(
                f"{s!r} is not a valid enum value. Allowed: {self.allowed_values}"
            )
        return s

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.name, "allowed_values": list(self.allowed_values)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Enum":
        return cls(allowed_values=d["allowed_values"])

    def __repr__(self) -> str:
        return f"Enum(allowed_values={self.allowed_values!r})"


# ---------------------------------------------------------------------------
# Type registry — maps YAML type names to their from_dict constructors
# ---------------------------------------------------------------------------

TYPE_REGISTRY: Dict[str, Type[DataType]] = {
    "Int64": Int64,
    "Int32": Int32,
    "Float64": Float64,
    "String": String,
    "Boolean": Boolean,
    "Date": Date,
    "Timestamp": Timestamp,
    "Enum": Enum,
}


def type_from_dict(d: Dict[str, Any]) -> DataType:
    """Deserialize a DataType from a plain dict.

    The dict must contain a ``type`` key whose value matches one of the
    registered type names (e.g. ``"Int64"``).

    Raises:
        ValueError: if the type name is not recognised.
    """
    type_name = d.get("type")
    if type_name not in TYPE_REGISTRY:
        raise ValueError(
            f"Unknown type {type_name!r}. Known types: {sorted(TYPE_REGISTRY)}"
        )
    return TYPE_REGISTRY[type_name].from_dict(d)
