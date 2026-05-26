"""Shared pytest fixtures for the datalasi test suite."""

import pytest

from datalasi import DataContract, Field, Float64, Int64, String, Enum, Timestamp


@pytest.fixture
def simple_contract():
    """A minimal contract with a handful of typed fields."""
    return DataContract(
        name="transactions",
        version="1.0.0",
        schema={
            "transaction_id": Field("transaction_id", Int64(), pk=True, nullable=False),
            "user_id": Field("user_id", Int64(), nullable=False),
            "amount": Field("amount", Float64(min=0.01, max=1_000_000), nullable=False),
            "status": Field(
                "status",
                Enum(["PENDING", "COMPLETED", "FAILED", "REFUNDED"]),
                nullable=False,
            ),
            "note": Field("note", String(max_length=255)),
            "timestamp": Field("timestamp", Timestamp(), nullable=False),
        },
        expectations=["amount > 0"],
        breaking_changes="FAIL",
        owner="data-eng@example.com",
        description="Financial transactions",
    )


@pytest.fixture
def empty_contract():
    """A contract with no fields."""
    return DataContract(name="empty", version="0.0.1", schema={})
