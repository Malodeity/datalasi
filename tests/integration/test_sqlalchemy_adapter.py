"""Integration tests for the SQLAlchemy adapter."""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pandas")

import pandas as pd  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from datalasi import DataContract, Field, Float64, Int64, String  # noqa: E402
from datalasi.adapters.sqlalchemy_adapter import SQLAlchemyAdapter  # noqa: E402


@pytest.fixture
def engine():
    eng = sa.create_engine("sqlite:///:memory:")
    with eng.connect() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE orders (
                    order_id INTEGER NOT NULL,
                    amount   REAL    NOT NULL,
                    note     TEXT
                )
                """
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO orders VALUES (1, 10.5, 'first'), (2, 20.0, NULL), (3, 15.5, 'third')"
            )
        )
        conn.commit()
    return eng


@pytest.fixture
def contract():
    return DataContract(
        name="orders",
        version="1.0.0",
        schema={
            "order_id": Field("order_id", Int64(), nullable=False),
            "amount": Field("amount", Float64(min=0.01), nullable=False),
            "note": Field("note", String()),
        },
        expectations=["amount > 0"],
    )


class TestFromCursorResult:
    def test_validate_success(self, engine, contract):
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT * FROM orders"))
            vr = SQLAlchemyAdapter.validate(result, contract)
        assert vr.success is True

    def test_row_count_metadata(self, engine, contract):
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT * FROM orders"))
            vr = SQLAlchemyAdapter.validate(result, contract)
        assert vr.metadata["row_count"] == 3

    def test_expectation_failure(self, engine):
        with engine.connect() as conn:
            conn.execute(sa.text("INSERT INTO orders VALUES (99, -5.0, 'bad')"))
            conn.commit()

        contract = DataContract(
            name="t",
            version="1.0.0",
            schema={"order_id": Field("order_id", Int64()), "amount": Field("amount", Float64())},
            expectations=["amount > 0"],
        )
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT order_id, amount FROM orders"))
            vr = SQLAlchemyAdapter.validate(result, contract)
        assert vr.success is False


class TestFromDataFrame:
    def test_dataframe_passthrough(self, contract):
        df = pd.DataFrame({"order_id": [1, 2], "amount": [5.0, 10.0], "note": ["a", None]})
        vr = SQLAlchemyAdapter.validate(df, contract)
        assert vr.success is True


class TestFromTable:
    def test_validate_with_table_object(self, engine, contract):
        metadata = sa.MetaData()
        orders_table = sa.Table("orders", metadata, autoload_with=engine)
        with engine.connect() as conn:
            vr = SQLAlchemyAdapter.validate(orders_table, contract, connection=conn)
        assert vr.success is True

    def test_table_without_connection_raises(self, engine, contract):
        metadata = sa.MetaData()
        orders_table = sa.Table("orders", metadata, autoload_with=engine)
        with pytest.raises(ValueError, match="connection is required"):
            SQLAlchemyAdapter.validate(orders_table, contract)


class TestInferSchema:
    def test_infer_from_cursor(self, engine):
        with engine.connect() as conn:
            result = conn.execute(sa.text("SELECT * FROM orders"))
            schema = SQLAlchemyAdapter.infer_schema(result)
        assert set(schema.keys()) == {"order_id", "amount", "note"}
