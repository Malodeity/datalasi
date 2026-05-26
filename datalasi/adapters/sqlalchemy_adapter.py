"""SQLAlchemy adapter for datalasi contract validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract, Field
    from datalasi.core.validation import ValidationResult


class SQLAlchemyAdapter:
    """Validate SQL query results or Table objects against a
    :class:`~datalasi.core.contract.DataContract`.

    Requires the ``sql`` optional dependency plus pandas::

        pip install "datalasi[sql,pandas]"

    Accepted inputs for *result*:

    - A **CursorResult** / **LegacyCursorResult** returned by
      ``connection.execute(...)`` — rows are fetched immediately.
    - A SQLAlchemy **Table** object — a ``SELECT *`` is issued using
      the supplied *connection*.
    - A SQLAlchemy **Select** construct — executed using *connection*.

    Example::

        from sqlalchemy import create_engine, text
        from datalasi import DataContract
        from datalasi.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

        engine = create_engine("sqlite:///mydb.db")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM orders"))
            validation = SQLAlchemyAdapter.validate(result, orders_contract)
    """

    @staticmethod
    def validate(
        result: Any,
        contract: DataContract,
        connection: Any = None,
    ) -> ValidationResult:
        """Validate *result* against *contract*.

        Args:
            result: A SQLAlchemy CursorResult, Table, or Select.
            contract: The DataContract to validate against.
            connection: Required when *result* is a Table or Select that
                has not yet been executed.

        Returns:
            A :class:`~datalasi.core.validation.ValidationResult`.
        """
        from datalasi.adapters.pandas_adapter import PandasAdapter

        df = SQLAlchemyAdapter._to_dataframe(result, connection)
        return PandasAdapter.validate(df, contract)

    @staticmethod
    def infer_schema(result: Any, connection: Any = None) -> dict[str, Field]:
        """Infer a contract schema from SQL query results.

        Returns:
            A dict mapping column name → :class:`~datalasi.core.contract.Field`.
        """
        from datalasi.adapters.pandas_adapter import PandasAdapter

        df = SQLAlchemyAdapter._to_dataframe(result, connection)
        return PandasAdapter.infer_schema(df)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dataframe(result: Any, connection: Any = None) -> Any:
        """Convert a SQLAlchemy result or table/select to a pandas DataFrame."""
        import pandas as pd

        # Already a DataFrame — pass through
        if isinstance(result, pd.DataFrame):
            return result

        # CursorResult / LegacyCursorResult (from connection.execute(...))
        if hasattr(result, "fetchall") and hasattr(result, "keys"):
            rows = result.fetchall()
            cols = list(result.keys())
            return pd.DataFrame(rows, columns=cols)

        # SQLAlchemy Table or Select — needs an active connection to execute
        if connection is None:
            raise ValueError(
                "A SQLAlchemy connection is required to execute a Table or Select. "
                "Pass it as: SQLAlchemyAdapter.validate(table, contract, connection=conn)"
            )

        stmt = result.select() if hasattr(result, "select") else result
        executed = connection.execute(stmt)
        rows = executed.fetchall()
        cols = list(executed.keys())
        return pd.DataFrame(rows, columns=cols)
