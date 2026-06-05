"""Core contract and field models for datalasi."""

from __future__ import annotations

from typing import Any, Literal

from datalasi.core.types import DataType, type_from_dict


class Field:
    """Describes a single column (field) in a data contract schema.

    Attributes:
        name: Column name.
        type: A :class:`DataType` instance describing the expected type.
        nullable: Whether the column may contain null/None values.
        pk: Whether this column is part of the primary key.
        description: Human-readable documentation for the column.
    """

    def __init__(
        self,
        name: str,
        type: DataType,  # noqa: A002  (shadowing built-in intentionally)
        nullable: bool = True,
        pk: bool = False,
        description: str | None = None,
    ) -> None:
        self.name = name
        self.type = type
        self.nullable = nullable
        self.pk = pk
        self.description = description

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize this field to a plain dict suitable for YAML output."""
        type_dict = self.type.to_dict()
        type_name = type_dict.pop("type")

        d: dict[str, Any] = {"type": type_name}
        d.update(type_dict)
        d["nullable"] = self.nullable
        if self.pk:
            d["pk"] = self.pk
        if self.description is not None:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> Field:
        """Deserialize a field from a plain dict (e.g. one YAML schema entry).

        The dict must contain a ``type`` key. All other type-specific keys
        (``min``, ``max``, ``allowed_values``, etc.) are passed through to the
        type's ``from_dict`` constructor.
        """
        field_type = type_from_dict(d)
        return cls(
            name=name,
            type=field_type,
            nullable=d.get("nullable", True),
            pk=d.get("pk", False),
            description=d.get("description"),
        )

    def __repr__(self) -> str:
        return (
            f"Field(name={self.name!r}, type={self.type!r}, "
            f"nullable={self.nullable}, pk={self.pk})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Field):
            return NotImplemented
        return (
            self.name == other.name
            and self.type == other.type
            and self.nullable == other.nullable
            and self.pk == other.pk
            and self.description == other.description
        )


class DataContract:
    """A versioned data schema contract.

    A ``DataContract`` describes the expected structure, types, nullability,
    and data-quality rules for a dataset. Contracts are serialised to YAML
    files and can be stored in Git for versioning.

    Attributes:
        name: Unique identifier for this contract (e.g. ``"transactions"``).
        version: Semantic version string (``"MAJOR.MINOR.PATCH"``).
        schema: Mapping of column name → :class:`Field`.
        expectations: List of expectation rule strings (e.g. ``"amount > 0"``).
            These are stored as-is in Phase 1; the adapter layer evaluates them.
        breaking_changes: How to respond to breaking-change violations.
            ``"FAIL"`` raises an error, ``"WARN"`` logs a warning,
            ``"IGNORE"`` silently proceeds.
        owner: Email or team identifier for the contract owner.
        description: Human-readable description of the dataset.
        tags: Arbitrary key/value metadata (e.g. ``{"pii": "true"}``).
    """

    def __init__(
        self,
        name: str,
        version: str,
        schema: dict[str, Field],
        expectations: list | None = None,
        breaking_changes: Literal["FAIL", "WARN", "IGNORE"] = "FAIL",
        owner: str | None = None,
        description: str | None = None,
        tags: dict[str, str] | None = None,
        extends: str | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.schema = schema
        self.expectations = expectations or []
        self.breaking_changes = breaking_changes
        self.owner = owner
        self.description = description
        self.tags = tags or {}
        self.extends = extends

    # ------------------------------------------------------------------
    # Field access helpers
    # ------------------------------------------------------------------

    def get_field(self, name: str) -> Field:
        """Return the :class:`Field` for *name*, raising KeyError if absent."""
        if name not in self.schema:
            raise KeyError(f"Field {name!r} not found in contract {self.name!r}")
        return self.schema[name]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the contract to a plain dict suitable for YAML output."""
        d: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "schema": {col: field.to_dict() for col, field in self.schema.items()},
            "expectations": [
                e.to_dict() if hasattr(e, "to_dict") else e for e in self.expectations
            ],
            "breaking_changes": self.breaking_changes,
        }
        if self.extends is not None:
            d["extends"] = self.extends
        if self.owner is not None:
            d["owner"] = self.owner
        if self.description is not None:
            d["description"] = self.description
        if self.tags:
            d["tags"] = dict(self.tags)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DataContract:
        """Deserialize a contract from a plain dict (e.g. loaded from YAML)."""
        from datalasi.core.expectations import ExpectationRule

        raw_schema = d.get("schema") or {}
        schema = {name: Field.from_dict(name, field_d) for name, field_d in raw_schema.items()}

        raw_expectations = d.get("expectations") or []
        expectations: list = []
        for e in raw_expectations:
            if isinstance(e, dict):
                expectations.append(ExpectationRule.from_dict(e))
            else:
                expectations.append(str(e))

        return cls(
            name=d["name"],
            version=d["version"],
            schema=schema,
            expectations=expectations,
            breaking_changes=d.get("breaking_changes", "FAIL"),
            owner=d.get("owner"),
            description=d.get("description"),
            tags=dict(d.get("tags") or {}),
            extends=d.get("extends"),
        )

    def to_yaml(self) -> str:
        """Render the contract as a YAML string."""
        import yaml  # lazy import — not needed for pure-Python use

        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def to_json(self) -> str:
        """Render the contract as a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=2)

    def to_json_schema(self) -> dict[str, Any]:
        """Export this contract as a JSON Schema (draft-07) document.

        Useful for generating validation schemas for REST APIs, form builders,
        and other tooling that speaks JSON Schema.

        Returns:
            A JSON-serialisable dict representing the schema.
        """
        from datalasi.export.json_schema import to_json_schema

        return to_json_schema(self)

    def to_avro_schema(self) -> dict[str, Any]:
        """Export this contract as an Apache Avro schema.

        Returns:
            A JSON-serialisable dict representing the Avro record schema.
        """
        from datalasi.export.avro import to_avro_schema

        return to_avro_schema(self)

    def to_dbt_schema(
        self,
        model_name: str | None = None,
        source_name: str | None = None,
    ) -> dict[str, Any]:
        """Export this contract as a dbt ``schema.yml`` structure.

        Generates ``not_null``, ``unique``, ``accepted_values``, and
        ``dbt_utils.expression_is_true`` tests from field metadata.

        Args:
            model_name: Override the dbt model name (defaults to ``self.name``).
            source_name: When set, wraps the entry in a ``sources`` block.

        Returns:
            A YAML-serialisable dict for use in a dbt project.
        """
        from datalasi.export.dbt import to_dbt_schema

        return to_dbt_schema(self, model_name=model_name, source_name=source_name)

    def to_dbt_schema_yaml(
        self,
        model_name: str | None = None,
        source_name: str | None = None,
    ) -> str:
        """Export this contract as a dbt ``schema.yml`` YAML string."""
        from datalasi.export.dbt import to_dbt_schema_yaml

        return to_dbt_schema_yaml(self, model_name=model_name, source_name=source_name)

    def to_pydantic(self) -> str:
        """Generate a Pydantic ``BaseModel`` source file from this contract.

        Returns a Python source string you can write to a ``.py`` file.
        Targets Pydantic v2 with Python 3.9+ compatibility.

        Example::

            Path("models/transactions.py").write_text(contract.to_pydantic())
        """
        from datalasi.export.pydantic_model import to_pydantic_source

        return to_pydantic_source(self)

    def to_pydantic_model(self) -> Any:
        """Return a live Pydantic ``BaseModel`` class built from this contract.

        Requires pydantic to be installed (``pip install pydantic``).

        Example::

            Order = contract.to_pydantic_model()
            order = Order(order_id=1, amount=99.99, status="COMPLETED")
        """
        from datalasi.export.pydantic_model import to_pydantic_model

        return to_pydantic_model(self)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Write this contract to a YAML file at *path*."""
        from datalasi.io.writers import YAMLWriter

        YAMLWriter.write(self, path)

    @classmethod
    def load(cls, path: str) -> DataContract:
        """Load a contract from a YAML file at *path*."""
        from datalasi.io.loaders import YAMLLoader

        return YAMLLoader.load(path)

    # ------------------------------------------------------------------
    # Validation (adapter dispatch — Phase 2)
    # ------------------------------------------------------------------

    def validate(self, df: Any, coerce: bool = False) -> Any:
        """Validate a DataFrame against this contract.

        Auto-detects whether *df* is a Pandas, Polars, or PyArrow DataFrame/Table
        and dispatches to the appropriate adapter.  Returns a
        :class:`~datalasi.core.validation.ValidationResult`.

        Args:
            df: A Pandas DataFrame, Polars DataFrame, or PyArrow Table.
            coerce: When ``True``, attempt to cast each column to its declared
                type before validation and record the coercions in
                ``result.coercions_applied``.  The original *df* is not mutated.

        Raises:
            ValueError: if *df* is not a supported DataFrame type.
            ImportError: if the required adapter library is not installed.
        """
        try:
            import pandas as pd

            if isinstance(df, pd.DataFrame):
                from datalasi.adapters.pandas_adapter import PandasAdapter

                return PandasAdapter.validate(df, self, coerce=coerce)
        except ImportError:
            pass

        try:
            import polars as pl

            if isinstance(df, pl.DataFrame):
                from datalasi.adapters.polars_adapter import PolarsAdapter

                return PolarsAdapter.validate(df, self, coerce=coerce)
        except ImportError:
            pass

        try:
            import pyarrow as pa

            if isinstance(df, pa.Table):
                from datalasi.adapters.arrow_adapter import ArrowAdapter

                return ArrowAdapter.validate(df, self)
        except ImportError:
            pass

        raise ValueError(
            f"Unsupported DataFrame type: {type(df).__name__}. "
            "Install datalasi[pandas], datalasi[polars], or datalasi[arrow]."
        )

    # ------------------------------------------------------------------
    # Contract inheritance
    # ------------------------------------------------------------------

    def resolve(self, registry: Any) -> DataContract:
        """Return a new contract with inherited fields merged from the parent.

        When ``self.extends`` is set, the parent contract's schema and
        expectations are fetched from *registry* (latest version) and merged
        with the child's definitions.  Child fields override parent fields of
        the same name.

        Args:
            registry: A :class:`~datalasi.io.registry.ContractRegistry` instance.

        Returns:
            A fully merged :class:`DataContract` (``self`` if ``extends`` is
            not set).
        """
        if not self.extends:
            return self

        parent = registry.get(self.extends)
        merged_schema = dict(parent.schema)
        merged_schema.update(self.schema)
        merged_expectations = list(parent.expectations) + [
            e for e in self.expectations if e not in parent.expectations
        ]

        return DataContract(
            name=self.name,
            version=self.version,
            schema=merged_schema,
            expectations=merged_expectations,
            breaking_changes=self.breaking_changes,
            owner=self.owner or parent.owner,
            description=self.description or parent.description,
            tags={**parent.tags, **self.tags},
            extends=self.extends,
        )

    # ------------------------------------------------------------------
    # Schema evolution
    # ------------------------------------------------------------------

    def evolve(self, **changes: Any) -> DataContract:
        """Return a new :class:`DataContract` with the given changes applied.

        Supported keyword arguments mirror the constructor parameters
        (``version``, ``schema``, ``expectations``, ``breaking_changes``,
        ``owner``, ``description``, ``tags``).

        Schema changes can be provided via ``schema_additions`` (dict of new
        fields) and ``schema_updates`` (dict of updated fields) rather than
        replacing the entire schema at once.

        Example::

            v2 = v1.evolve(
                version="1.1.0",
                schema_additions={"currency": Field("currency", String)},
            )
        """
        new_schema = dict(self.schema)
        if "schema_additions" in changes:
            new_schema.update(changes.pop("schema_additions"))
        if "schema_updates" in changes:
            new_schema.update(changes.pop("schema_updates"))
        if "schema" in changes:
            new_schema = changes.pop("schema")

        return DataContract(
            name=changes.get("name", self.name),
            version=changes.get("version", self.version),
            schema=new_schema,
            expectations=changes.get("expectations", list(self.expectations)),
            breaking_changes=changes.get("breaking_changes", self.breaking_changes),
            owner=changes.get("owner", self.owner),
            description=changes.get("description", self.description),
            tags=changes.get("tags", dict(self.tags)),
            extends=changes.get("extends", self.extends),
        )

    def __repr__(self) -> str:
        return f"DataContract(name={self.name!r}, version={self.version!r}, fields={list(self.schema)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DataContract):
            return NotImplemented
        return self.to_dict() == other.to_dict()
