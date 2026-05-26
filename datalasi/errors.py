"""Custom exceptions for datalasi."""


class ContractError(Exception):
    """Base exception for all datalasi errors."""


class SchemaValidationError(ContractError):
    """Raised when a DataFrame fails schema validation."""

    def __init__(self, message: str, violations: list = None):
        super().__init__(message)
        self.violations = violations or []


class TypeValidationError(ContractError):
    """Raised when a value cannot be coerced to the expected type."""


class ContractNotFoundError(ContractError):
    """Raised when a contract cannot be found in the registry."""


class ContractLoadError(ContractError):
    """Raised when a contract file cannot be loaded or parsed."""
