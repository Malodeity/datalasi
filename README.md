# datalasi

**Schema contracts for your data pipelines — defined as code, enforced at runtime.**

---

## The problem

Data pipelines break silently. A column gets renamed. A type changes from `string` to `integer`. An enum gains a new value that downstream code doesn't handle. By the time anyone notices, bad data has already flowed into dashboards, ML features, or production databases.

The standard fixes all have gaps:

| Approach | What it misses |
|---|---|
| Unit tests | Schema drift between services and data sources |
| dbt tests | Run *after* data lands in the warehouse — too late |
| Great Expectations | Heavyweight: server, UI, significant setup |
| Informal docs | Forgotten the moment they're written |

**datalasi** takes a different approach: treat data schemas like code. Define them as versioned YAML files, commit them to Git, validate DataFrames against them inline, and gate your CI pipeline on breaking changes.

---

## How it works

**1. Define your schema as a contract**

```yaml
# contracts/transactions-v1.0.0.yaml
name: transactions
version: 1.0.0
owner: data-eng@company.com

schema:
  transaction_id:
    type: Int64
    nullable: false
    pk: true

  amount:
    type: Float64
    nullable: false
    min: 0.01

  status:
    type: Enum
    allowed_values: [PENDING, COMPLETED, FAILED]
    nullable: false

expectations:
  - "amount > 0"
  - column: amount
    rule: gt
    value: 0
    description: "Amount must be positive"
    severity: WARNING
```

**2. Validate your DataFrame**

```python
from datalasi import DataContract

contract = DataContract.load("contracts/transactions-v1.0.0.yaml")
result = contract.validate(df)   # pandas, polars, pyarrow — auto-detected

if not result.success:
    print(result)   # rich-formatted table of schema violations and expectation failures
```

**3. Gate CI on breaking changes**

```bash
# exits 1 if this version introduces breaking changes vs its predecessor
datalasi check contracts/ transactions
```

**4. Export to the tools your team already uses**

```python
# dbt schema.yml with not_null / unique / accepted_values tests auto-generated
contract.to_dbt_schema_yaml()

# Pydantic BaseModel — save to a .py file or use at runtime
contract.to_pydantic()           # Python source string
contract.to_pydantic_model()     # live class via create_model()

# JSON Schema (draft-07) and Apache Avro
contract.to_json_schema()
contract.to_avro_schema()
```

---

## Installation

```bash
pip install datalasi                    # core (includes rich CLI output)
pip install "datalasi[pandas]"          # + pandas validation
pip install "datalasi[polars]"          # + polars validation
pip install "datalasi[arrow]"           # + pyarrow validation
pip install "datalasi[sql]"             # + sqlalchemy validation
pip install "datalasi[git]"             # + git-backed versioning
pip install "datalasi[all]"             # everything
```

---

## Features

### DataFrame validation — pandas, polars, pyarrow, SQLAlchemy

```python
from datalasi.adapters.pandas_adapter import PandasAdapter
from datalasi.adapters.polars_adapter import PolarsAdapter
from datalasi.adapters.arrow_adapter import ArrowAdapter
from datalasi.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

result = PandasAdapter.validate(pandas_df, contract)
result = PolarsAdapter.validate(polars_df, contract)
result = ArrowAdapter.validate(arrow_table, contract)

# SQLAlchemy — CursorResult, Table, or Select
with engine.connect() as conn:
    result = SQLAlchemyAdapter.validate(
        conn.execute(text("SELECT * FROM orders")), contract
    )
```

### Coercion mode

```python
# cast columns to their declared types before validation
result = contract.validate(df, coerce=True)
print(result.coercions_applied)
# ["amount: object → Float64", "quantity: float64 → Int64"]
```

### Structured expectations DSL

```python
from datalasi import ExpectationRule

contract = DataContract(
    name="orders",
    version="1.0.0",
    schema={...},
    expectations=[
        "amount > 0",                                               # plain string
        ExpectationRule("status", "in", ["OPEN", "CLOSED"]),        # structured
        ExpectationRule("email", "regex", r".*@.*\..*",
                        description="Valid email format",
                        severity="WARNING"),                         # warning — records but doesn't fail
    ],
)
```

### dbt integration

```python
# generates not_null, unique, accepted_values, dbt_utils.expression_is_true
yaml_str = contract.to_dbt_schema_yaml()
Path("models/staging/schema.yml").write_text(yaml_str)

# or via CLI
# datalasi dbt contracts/transactions-v1.0.0.yaml --output models/staging/schema.yml

# sources block for staging layer
contract.to_dbt_schema(source_name="raw_postgres")
```

Example output:
```yaml
version: 2
models:
  - name: transactions
    description: Customer transaction records
    columns:
      - name: transaction_id
        tests:
          - not_null
          - unique
      - name: amount
        tests:
          - not_null
          - dbt_utils.expression_is_true:
              expression: amount >= 0.01
      - name: status
        tests:
          - not_null
          - accepted_values:
              values: [PENDING, COMPLETED, FAILED]
```

### Pydantic model generation

```python
# Save a typed BaseModel to a .py file
Path("models/transactions.py").write_text(contract.to_pydantic())

# Or get a live class immediately (no file needed)
Transactions = contract.to_pydantic_model()
tx = Transactions(transaction_id=1, amount=99.99, status="COMPLETED")
```

Generated source:
```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class Transactions(BaseModel):
    """Customer transaction records."""

    transaction_id: int
    amount: float = Field(..., ge=0.01)
    status: Literal["PENDING", "COMPLETED", "FAILED"]
    note: str | None = None
```

### Contract inheritance

```python
# child inherits all fields from parent and adds its own
express_contract = DataContract(
    name="orders_express",
    version="1.0.0",
    extends="orders",
    schema={
        "delivery_date": Field("delivery_date", Date(), nullable=False),
    },
)

registry = ContractRegistry("contracts/")
merged = express_contract.resolve(registry)
```

### JSON Schema and Avro export

```python
# JSON Schema (draft-07) — for REST APIs, OpenAPI, form validators
js = contract.to_json_schema()

# Apache Avro — for Kafka topics, data lake ingestion
avro = contract.to_avro_schema()
```

### Git-backed versioning

```python
from datalasi.io import GitBackend

backend = GitBackend(".")
sha = backend.commit_contract(contract, "contracts/orders-v1.1.0.yaml")

for entry in backend.history("contracts/orders-v1.1.0.yaml"):
    print(entry["sha"], entry["date"], entry["message"])

past_contract = backend.get_at_commit("contracts/orders-v1.1.0.yaml", sha)
```

### Contract registry and breaking-change detection

```python
from datalasi.io import ContractRegistry

registry = ContractRegistry("contracts/")
contract = registry.get("transactions")            # latest version
v1 = registry.get("transactions", version="1.0.0")
diff = registry.diff("transactions", "1.0.0", "1.1.0")

print(diff.has_breaking_changes)   # True / False
print(diff.breaking_changes)       # ["Column 'amount' changed nullable → non-nullable"]
```

### VS Code YAML autocomplete

Add to `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "./datalasi-schema.json": ["contracts/**/*.yaml"]
  }
}
```

---

## CLI

```bash
# Interactively create a contract
datalasi init

# Validate a data file against a contract
datalasi validate contracts/transactions-v1.0.0.yaml data/tx.csv

# Infer a contract from a data file
datalasi infer data/transactions.parquet --name transactions --output contracts/tx-v1.0.0.yaml

# List all contracts in a registry
datalasi list --registry contracts/

# Diff two versions
datalasi diff contracts/ transactions 1.0.0 1.1.0

# CI gate — exit 1 if latest version has breaking changes vs predecessor
datalasi check contracts/ transactions

# Generate a dbt schema.yml
datalasi dbt contracts/transactions-v1.0.0.yaml --output models/staging/schema.yml

# Generate a Pydantic model
datalasi pydantic contracts/transactions-v1.0.0.yaml --output models/transactions.py
```

---

## Supported types

| Type | Description | Constraints |
|------|-------------|-------------|
| `Int64` | 64-bit integer | `min`, `max` |
| `Int32` | 32-bit integer | `min`, `max` |
| `Float64` | 64-bit float | `min`, `max` |
| `String` | Text | `max_length`, `pattern` |
| `Boolean` | True/False | — |
| `Date` | YYYY-MM-DD | — |
| `Timestamp` | ISO datetime | `timezone` |
| `Enum` | Fixed value set | `allowed_values` |

---

## Development

```bash
git clone https://github.com/Malodeity/datalasi
cd datalasi
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,pandas,polars,arrow,sql,git]"

pytest tests/ -v --cov=datalasi
ruff check datalasi tests
black datalasi tests
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
