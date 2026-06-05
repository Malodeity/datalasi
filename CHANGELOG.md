# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-05

### Added
- **dbt schema.yml export** — `contract.to_dbt_schema()` / `contract.to_dbt_schema_yaml()`
  generate a ready-to-use dbt schema file with `not_null`, `unique`, `accepted_values`,
  and `dbt_utils.expression_is_true` tests inferred from field metadata; supports both
  model and source blocks; `datalasi dbt <contract> --output <path>` CLI command
- **Pydantic model generation** (two modes):
  - `contract.to_pydantic()` — Python source string with a typed `BaseModel` class,
    `Literal[...]` for Enum fields, `datetime.date` / `datetime.datetime` for temporal
    types, and `ge` / `le` / `max_length` validators; `datalasi pydantic <contract>` CLI
  - `contract.to_pydantic_model()` — live `BaseModel` class via `pydantic.create_model`,
    usable immediately without writing any file
- **Rich terminal output** — all CLI formatters rewritten with
  [Rich](https://github.com/Textualize/rich): bordered Panels for validation results,
  colour-coded violation Tables, structured diff output with ✗ / + icons, and a
  registry summary Table with latest version highlighted; `rich>=13.0` added as a
  core dependency

## [0.2.0] - 2026-06-05

### Added
- **PyArrow adapter** (`ArrowAdapter`) — validate PyArrow Tables natively with schema
  checks, nullability, Enum value validation, and expectation evaluation via pandas
- **SQLAlchemy adapter** (`SQLAlchemyAdapter`) — accepts `CursorResult`, `Table`, or
  `Select`; converts to pandas DataFrame internally
- **Contract inheritance** — `extends: "parent_name"` field in YAML; `contract.resolve(registry)`
  merges parent schema + expectations, child fields override parent
- **Coercion mode** — `contract.validate(df, coerce=True)` casts columns to their
  declared types before validation; coercions recorded in `result.coercions_applied`
- **Structured expectations DSL** (`ExpectationRule`) — column-level rules with
  `rule` types (`gt`, `gte`, `lt`, `lte`, `eq`, `ne`, `in`, `not_in`, `regex`,
  `between`, `not_null`, `unique`), `severity="WARNING"` support, pandas
  `to_expression()` and Polars `to_polars_expr()` generation, full YAML roundtrip
- **JSON Schema export** — `contract.to_json_schema()` produces a draft-07 document
  with type constraints, `anyOf` nullable wrappers, and enum lists
- **Avro schema export** — `contract.to_avro_schema()` produces an Avro record schema
  with `date` / `timestamp-millis` logical types
- **Git-backed versioning** (`GitBackend`) — `commit_contract()`, `history()`,
  `get_at_commit()` using gitpython
- **`datalasi init`** — interactive wizard that creates a contract YAML from prompts
- **`datalasi check`** — CI gate that diffs the latest contract version against its
  predecessor; exits 1 on breaking changes
- **VS Code JSON Schema** (`datalasi-schema.json`) — drop into your workspace for
  YAML autocomplete and validation when editing contract files
- `DataContract.validate()` now auto-dispatches to the PyArrow adapter for
  `pa.Table` inputs
- 321 tests, 83% coverage

## [0.1.0] - 2026-05-26

### Added
- Core type system: `Int64`, `Int32`, `Float64`, `String`, `Boolean`, `Date`, `Timestamp`, `Enum`
  — each with `validate()`, `coerce()`, `to_dict()`, `from_dict()`
- `Field` and `DataContract` model with full YAML serialization roundtrip
- `YAMLLoader` and `YAMLWriter` for Git-friendly contract persistence
- `DataContract.evolve()` for non-destructive schema evolution
- `DataContract.validate(df)` — auto-dispatches to Pandas or Polars adapter
- **Pandas adapter** — schema validation, nullability checks, Enum value checking,
  expectation evaluation, metadata collection, `infer_schema()`
- **Polars adapter** — full feature parity with Pandas adapter
- **Contract registry** (`ContractRegistry`) — directory-backed, semver-sorted,
  with full breaking-change detection:
  - Removed columns, type changes, nullability tightening
  - Enum value removal, numeric constraint tightening, string `max_length` tightening
- `ContractDiff` — structured diff result with `breaking_changes`, `non_breaking_changes`, `summary`
- **CLI** (`datalasi` command):
  - `datalasi validate <contract> <data>` — validate CSV/Parquet against a contract
  - `datalasi infer <data> --name <name> --output <path>` — infer contract from data
  - `datalasi list --registry <dir>` — list all contracts and versions
  - `datalasi diff <registry> <name> <v1> <v2>` — show breaking/non-breaking changes
- 229 tests, 87% coverage
- GitHub Actions CI/CD workflow (Python 3.9–3.12 matrix)
- Apache 2.0 license

[0.3.0]: https://github.com/Malodeity/datalasi/releases/tag/v0.3.0
[0.2.0]: https://github.com/Malodeity/datalasi/releases/tag/v0.2.0
[0.1.0]: https://github.com/Malodeity/datalasi/releases/tag/v0.1.0
