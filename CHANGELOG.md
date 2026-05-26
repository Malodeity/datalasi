# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/malodeity/datalasi/releases/tag/v0.1.0
