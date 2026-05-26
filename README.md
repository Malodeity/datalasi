# datalasi

**Versioned data schema enforcement for Python.**

Define data contracts as YAML files, version them in Git, and validate DataFrames against them. Think: `pytest` for your data schemas, with semantic versioning.

```python
from datalasi import DataContract, Field, Int64, Float64, Enum
from datalasi.io import YAMLWriter, YAMLLoader

contract = DataContract(
    name="transactions",
    version="1.0.0",
    schema={
        "transaction_id": Field("transaction_id", Int64(), pk=True, nullable=False),
        "amount":         Field("amount", Float64(min=0.01), nullable=False),
        "status":         Field("status", Enum(["PENDING", "COMPLETED", "FAILED"]), nullable=False),
    },
    expectations=["amount > 0"],
    owner="data-eng@example.com",
)

# Save to YAML (Git-versioned)
YAMLWriter.write(contract, "contracts/transactions-v1.0.0.yaml")

# Load from YAML
loaded = YAMLLoader.load("contracts/transactions-v1.0.0.yaml")
assert loaded == contract
```

## Installation

```bash
pip install datalasi
```

With optional adapters:

```bash
pip install "datalasi[pandas]"   # Pandas DataFrame validation
pip install "datalasi[polars]"   # Polars DataFrame validation
pip install "datalasi[all]"      # All adapters
```

## Core Concepts

### DataContract

A contract describes the expected structure of a dataset:

- **name** — unique identifier (e.g. `transactions`)
- **version** — semantic version (`MAJOR.MINOR.PATCH`)
- **schema** — column definitions with types, nullability, constraints
- **expectations** — data-quality rules (stored as strings, evaluated by adapters)
- **breaking_changes** — `FAIL`, `WARN`, or `IGNORE`

### Field

Each field carries a `DataType` plus metadata:

```python
Field("amount", Float64(min=0.01, max=1_000_000), nullable=False, description="USD amount")
```

### Supported Types

| Type | Description | Constraints |
|------|-------------|-------------|
| `Int64` | 64-bit integer | `min`, `max` |
| `Int32` | 32-bit integer | `min`, `max` |
| `Float64` | 64-bit float | `min`, `max` |
| `String` | Text | `max_length`, `pattern` |
| `Boolean` | True/False | — |
| `Date` | YYYY-MM-DD string | — |
| `Timestamp` | ISO datetime string | `timezone` |
| `Enum` | Fixed value set | `allowed_values` |

### YAML Contract Format

```yaml
name: transactions
version: 1.0.0
owner: data-eng@company.com
breaking_changes: FAIL

schema:
  transaction_id:
    type: Int64
    nullable: false
    pk: true

  amount:
    type: Float64
    nullable: false
    min: 0.01
    max: 1000000

  status:
    type: Enum
    allowed_values: [PENDING, COMPLETED, FAILED]
    nullable: false

expectations:
  - "amount > 0"
```

### Schema Evolution

```python
v2 = v1.evolve(
    version="1.1.0",
    schema_additions={"currency": Field("currency", String(), description="ISO 4217 code")},
)
```

## Development

```bash
git clone https://github.com/malomthethwa/datalasi
cd datalasi
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ -v --cov=datalasi

# Lint & format
ruff check datalasi tests
black datalasi tests
mypy datalasi
```

## Building & Publishing to PyPI

```bash
pip install build twine

# Build distribution
python -m build

# Upload to PyPI
twine upload dist/*
```

## Roadmap

- **0.1.0** — Core type system, YAML I/O, contract model ✓
- **0.2.0** — Pandas & Polars adapters, DataFrame validation
- **0.3.0** — CLI (`datalasi validate`, `datalasi infer`, `datalasi diff`)
- **0.4.0** — Contract registry, breaking-change detection, migration scripts

## License

Apache 2.0 — see [LICENSE](LICENSE).
