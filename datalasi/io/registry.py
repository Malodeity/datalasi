"""Contract registry — load, browse, and diff versioned contracts from a directory."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from datalasi.core.contract import DataContract
from datalasi.errors import ContractNotFoundError


# ---------------------------------------------------------------------------
# Semver comparison helper
# ---------------------------------------------------------------------------


def _parse_version(version: str) -> Tuple[int, int, int]:
    """Parse a semver string into a (major, minor, patch) tuple.

    Strips a leading ``v`` if present (e.g. ``"v1.2.3"`` → ``(1, 2, 3)``).
    Raises ValueError for non-semver strings.
    """
    cleaned = version.lstrip("v")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+).*", cleaned)
    if not match:
        raise ValueError(f"Cannot parse version {version!r} as semver")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


# ---------------------------------------------------------------------------
# Diff result
# ---------------------------------------------------------------------------


@dataclass
class ContractDiff:
    """Result of comparing two contract versions.

    Attributes:
        name: Contract name.
        v1: The older version string.
        v2: The newer version string.
        breaking_changes: List of breaking change descriptions.
        non_breaking_changes: List of non-breaking change descriptions.
    """

    name: str
    v1: str
    v2: str
    breaking_changes: List[str] = field(default_factory=list)
    non_breaking_changes: List[str] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        return bool(self.breaking_changes)

    @property
    def summary(self) -> str:
        parts = []
        if self.breaking_changes:
            parts.append(f"{len(self.breaking_changes)} breaking change(s)")
        if self.non_breaking_changes:
            parts.append(f"{len(self.non_breaking_changes)} non-breaking change(s)")
        if not parts:
            return f"No schema changes between {self.v1} and {self.v2}"
        return f"{self.name} {self.v1} → {self.v2}: " + ", ".join(parts)

    def __str__(self) -> str:
        lines = [self.summary]
        if self.breaking_changes:
            lines.append("Breaking changes:")
            for c in self.breaking_changes:
                lines.append(f"  ✗ {c}")
        if self.non_breaking_changes:
            lines.append("Non-breaking changes:")
            for c in self.non_breaking_changes:
                lines.append(f"  + {c}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ContractRegistry:
    """A directory-backed registry of versioned data contracts.

    Contracts are stored as YAML files anywhere under *registry_dir* (the
    directory is scanned recursively). Each YAML file must contain a valid
    ``DataContract`` document with ``name`` and ``version`` fields.

    Example layout::

        contracts/
        ├── transactions/
        │   ├── v1.0.0.yaml
        │   └── v1.1.0.yaml
        └── user_features/
            └── v1.0.0.yaml

    Usage::

        registry = ContractRegistry("contracts/")
        contract = registry.get("transactions")           # latest version
        v1 = registry.get("transactions", version="1.0.0")
        diff = registry.diff("transactions", "1.0.0", "1.1.0")
    """

    def __init__(self, registry_dir: str) -> None:
        self.registry_dir = Path(registry_dir)
        # Mapping of "name:version" → DataContract
        self._contracts: Dict[str, DataContract] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Scan *registry_dir* recursively for YAML contract files."""
        from datalasi.errors import ContractLoadError
        from datalasi.io.loaders import YAMLLoader

        if not self.registry_dir.exists():
            return

        for yaml_file in sorted(self.registry_dir.glob("**/*.yaml")):
            try:
                contract = YAMLLoader.load(str(yaml_file))
                key = f"{contract.name}:{contract.version}"
                self._contracts[key] = contract
            except (ContractLoadError, Exception):
                # Skip files that aren't valid contracts
                pass

    def reload(self) -> None:
        """Re-scan the registry directory (useful after adding new files)."""
        self._contracts.clear()
        self._load_all()

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, name: str, version: Optional[str] = None) -> DataContract:
        """Retrieve a contract by name and optionally by version.

        If *version* is omitted, returns the latest version (sorted by semver).

        Raises:
            ContractNotFoundError: if no matching contract is found.
        """
        matching = [
            c for key, c in self._contracts.items() if key.startswith(f"{name}:")
        ]
        if not matching:
            raise ContractNotFoundError(
                f"No contract named {name!r} found in registry {self.registry_dir}"
            )

        if version is not None:
            for c in matching:
                if c.version == version:
                    return c
            raise ContractNotFoundError(
                f"Contract {name!r} version {version!r} not found. "
                f"Available: {[c.version for c in matching]}"
            )

        # Return latest by semver
        try:
            return max(matching, key=lambda c: _parse_version(c.version))
        except ValueError:
            # Fall back to lexicographic sort if version isn't semver
            return sorted(matching, key=lambda c: c.version)[-1]

    def list_contracts(self) -> Dict[str, List[str]]:
        """Return a dict mapping contract name → sorted list of versions."""
        result: Dict[str, List[str]] = {}
        for c in self._contracts.values():
            result.setdefault(c.name, [])
            result[c.name].append(c.version)

        for name in result:
            try:
                result[name] = sorted(result[name], key=_parse_version)
            except ValueError:
                result[name] = sorted(result[name])

        return result

    # ------------------------------------------------------------------
    # Diff / breaking change detection
    # ------------------------------------------------------------------

    def diff(self, name: str, v1: str, v2: str) -> ContractDiff:
        """Compare two versions of a contract and return a
        :class:`ContractDiff` with breaking and non-breaking changes.

        Raises:
            ContractNotFoundError: if either version is not in the registry.
        """
        old = self.get(name, version=v1)
        new = self.get(name, version=v2)
        breaking, non_breaking = _detect_changes(old, new)
        return ContractDiff(
            name=name,
            v1=v1,
            v2=v2,
            breaking_changes=breaking,
            non_breaking_changes=non_breaking,
        )

    def breaking_changes_between(self, name: str, v1: str, v2: str) -> List[str]:
        """Return only the list of breaking change descriptions."""
        return self.diff(name, v1, v2).breaking_changes

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._contracts)

    def __repr__(self) -> str:
        return f"ContractRegistry(dir={self.registry_dir!r}, contracts={len(self)})"


# ---------------------------------------------------------------------------
# Breaking change detection
# ---------------------------------------------------------------------------


def _detect_changes(
    old: DataContract, new: DataContract
) -> Tuple[List[str], List[str]]:
    """Compare two contracts and return (breaking_changes, non_breaking_changes)."""
    from datalasi.core.types import Enum as EnumType

    breaking: List[str] = []
    non_breaking: List[str] = []

    old_schema = old.schema
    new_schema = new.schema

    # Removed columns — always breaking
    for col in old_schema:
        if col not in new_schema:
            breaking.append(f"Column '{col}' removed")

    # Added columns — non-breaking
    for col in new_schema:
        if col not in old_schema:
            non_breaking.append(f"Column '{col}' added")

    # Changed columns
    for col in old_schema:
        if col not in new_schema:
            continue

        old_f = old_schema[col]
        new_f = new_schema[col]

        # Type name change — breaking
        if old_f.type.name != new_f.type.name:
            breaking.append(
                f"Column '{col}' type changed from {old_f.type.name} to {new_f.type.name}"
            )
            continue  # Further checks below are only meaningful if types match

        # Nullability: nullable → non-nullable is breaking
        if old_f.nullable and not new_f.nullable:
            breaking.append(f"Column '{col}' changed from nullable to non-nullable")
        elif not old_f.nullable and new_f.nullable:
            non_breaking.append(f"Column '{col}' changed from non-nullable to nullable")

        # Enum: removed allowed values are breaking, added are non-breaking
        if isinstance(old_f.type, EnumType) and isinstance(new_f.type, EnumType):
            old_vals = set(old_f.type.allowed_values)
            new_vals = set(new_f.type.allowed_values)
            removed = old_vals - new_vals
            added = new_vals - old_vals
            if removed:
                breaking.append(
                    f"Column '{col}' Enum removed allowed value(s): {sorted(removed)}"
                )
            if added:
                non_breaking.append(
                    f"Column '{col}' Enum added allowed value(s): {sorted(added)}"
                )

        # Numeric constraints (Int64, Int32, Float64)
        if old_f.type.name in ("Int64", "Int32", "Float64"):
            _check_numeric_constraints(col, old_f.type, new_f.type, breaking, non_breaking)

        # String max_length constraint
        if old_f.type.name == "String":
            _check_string_constraints(col, old_f.type, new_f.type, breaking, non_breaking)

    return breaking, non_breaking


def _check_numeric_constraints(
    col: str,
    old_type: Any,
    new_type: Any,
    breaking: List[str],
    non_breaking: List[str],
) -> None:
    old_min = getattr(old_type, "min", None)
    new_min = getattr(new_type, "min", None)
    old_max = getattr(old_type, "max", None)
    new_max = getattr(new_type, "max", None)

    # min increased or newly added → breaking (old valid data may now be below min)
    if new_min is not None and (old_min is None or new_min > old_min):
        breaking.append(
            f"Column '{col}' min constraint tightened: {old_min!r} → {new_min!r}"
        )
    elif old_min is not None and (new_min is None or new_min < old_min):
        non_breaking.append(f"Column '{col}' min constraint relaxed")

    # max decreased or newly added → breaking
    if new_max is not None and (old_max is None or new_max < old_max):
        breaking.append(
            f"Column '{col}' max constraint tightened: {old_max!r} → {new_max!r}"
        )
    elif old_max is not None and (new_max is None or new_max > old_max):
        non_breaking.append(f"Column '{col}' max constraint relaxed")


def _check_string_constraints(
    col: str,
    old_type: Any,
    new_type: Any,
    breaking: List[str],
    non_breaking: List[str],
) -> None:
    old_len = getattr(old_type, "max_length", None)
    new_len = getattr(new_type, "max_length", None)

    if new_len is not None and (old_len is None or new_len < old_len):
        breaking.append(
            f"Column '{col}' max_length tightened: {old_len!r} → {new_len!r}"
        )
    elif old_len is not None and (new_len is None or new_len > old_len):
        non_breaking.append(f"Column '{col}' max_length relaxed")


# Fix missing Any import used in type hints inside functions
from typing import Any  # noqa: E402
