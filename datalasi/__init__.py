"""datalasi — versioned data schema enforcement for Python.

Quick start::

    from datalasi import DataContract, Field, Int64, Float64, String, Enum
    from datalasi.io import YAMLWriter, YAMLLoader

    contract = DataContract(
        name="transactions",
        version="1.0.0",
        schema={
            "transaction_id": Field("transaction_id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01), nullable=False),
            "status": Field(
                "status",
                Enum(["PENDING", "COMPLETED", "FAILED"]),
                nullable=False,
            ),
        },
        expectations=["amount > 0"],
        owner="data-eng@example.com",
    )

    YAMLWriter.write(contract, "contracts/transactions-v1.0.0.yaml")
    loaded = YAMLLoader.load("contracts/transactions-v1.0.0.yaml")
    assert loaded == contract
"""

from datalasi.core.contract import DataContract, Field
from datalasi.core.types import (
    Boolean,
    DataType,
    Date,
    Enum,
    Float64,
    Int32,
    Int64,
    String,
    Timestamp,
)
from datalasi.core.validation import (
    ExpectationViolation,
    SchemaViolation,
    ValidationResult,
)
from datalasi.errors import (
    ContractError,
    ContractLoadError,
    ContractNotFoundError,
    SchemaValidationError,
    TypeValidationError,
)
from datalasi.io.registry import ContractRegistry, ContractDiff
from datalasi.version import __version__

__all__ = [
    "__version__",
    # Registry
    "ContractRegistry",
    "ContractDiff",
    # Contract model
    "DataContract",
    "Field",
    # Types
    "DataType",
    "Int64",
    "Int32",
    "Float64",
    "String",
    "Boolean",
    "Date",
    "Timestamp",
    "Enum",
    # Validation results
    "ValidationResult",
    "SchemaViolation",
    "ExpectationViolation",
    # Errors
    "ContractError",
    "SchemaValidationError",
    "TypeValidationError",
    "ContractLoadError",
    "ContractNotFoundError",
]
