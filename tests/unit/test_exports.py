"""Unit tests for JSON Schema and Avro schema export."""

from __future__ import annotations

import pytest

from datalasi import DataContract, Enum, Field, Float64, Int32, Int64, String
from datalasi.core.types import Boolean, Date, Timestamp
from datalasi.export.avro import to_avro_schema
from datalasi.export.json_schema import to_json_schema


@pytest.fixture
def contract():
    return DataContract(
        name="orders",
        version="1.0.0",
        description="Customer order records",
        schema={
            "order_id": Field("order_id", Int64(), pk=True, nullable=False),
            "amount": Field("amount", Float64(min=0.01, max=1_000_000), nullable=False),
            "status": Field(
                "status",
                Enum(["PENDING", "COMPLETED", "CANCELLED"]),
                nullable=False,
                description="Order status",
            ),
            "note": Field("note", String(max_length=500)),
            "quantity": Field("quantity", Int32(), nullable=False),
        },
    )


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------


class TestToJsonSchema:
    def test_schema_key(self, contract):
        js = to_json_schema(contract)
        assert js["$schema"] == "http://json-schema.org/draft-07/schema#"

    def test_title(self, contract):
        js = to_json_schema(contract)
        assert js["title"] == "orders"

    def test_description(self, contract):
        js = to_json_schema(contract)
        assert "order records" in js["description"].lower()

    def test_properties_keys(self, contract):
        js = to_json_schema(contract)
        assert set(js["properties"].keys()) == {"order_id", "amount", "status", "note", "quantity"}

    def test_required_lists_non_nullable(self, contract):
        js = to_json_schema(contract)
        required = set(js["required"])
        assert "order_id" in required
        assert "amount" in required
        assert "note" not in required

    def test_integer_type(self, contract):
        js = to_json_schema(contract)
        assert js["properties"]["order_id"]["type"] == "integer"

    def test_number_type(self, contract):
        js = to_json_schema(contract)
        prop = js["properties"]["amount"]
        assert prop["type"] == "number"
        assert prop["minimum"] == 0.01
        assert prop["maximum"] == 1_000_000

    def test_enum_type(self, contract):
        js = to_json_schema(contract)
        prop = js["properties"]["status"]
        assert prop["type"] == "string"
        assert set(prop["enum"]) == {"PENDING", "COMPLETED", "CANCELLED"}

    def test_string_max_length(self, contract):
        js = to_json_schema(contract)
        # note is nullable so it's wrapped in anyOf
        note_prop = js["properties"]["note"]
        inner = note_prop["anyOf"][0]
        assert inner.get("maxLength") == 500

    def test_nullable_uses_anyof(self, contract):
        js = to_json_schema(contract)
        note = js["properties"]["note"]
        assert "anyOf" in note
        types = [p.get("type") for p in note["anyOf"]]
        assert "null" in types

    def test_field_description_included(self, contract):
        js = to_json_schema(contract)
        assert js["properties"]["status"]["description"] == "Order status"

    def test_boolean_type(self):
        c = DataContract(
            name="t",
            version="1.0.0",
            schema={"flag": Field("flag", Boolean(), nullable=False)},
        )
        js = to_json_schema(c)
        assert js["properties"]["flag"]["type"] == "boolean"

    def test_date_format(self):
        c = DataContract(
            name="t",
            version="1.0.0",
            schema={"dt": Field("dt", Date(), nullable=False)},
        )
        js = to_json_schema(c)
        prop = js["properties"]["dt"]
        assert prop["format"] == "date"

    def test_timestamp_format(self):
        c = DataContract(
            name="t",
            version="1.0.0",
            schema={"ts": Field("ts", Timestamp(), nullable=False)},
        )
        js = to_json_schema(c)
        assert js["properties"]["ts"]["format"] == "date-time"

    def test_convenience_method_on_contract(self, contract):
        assert contract.to_json_schema() == to_json_schema(contract)


# ---------------------------------------------------------------------------
# Avro Schema
# ---------------------------------------------------------------------------


class TestToAvroSchema:
    def test_type_record(self, contract):
        avro = to_avro_schema(contract)
        assert avro["type"] == "record"

    def test_name(self, contract):
        avro = to_avro_schema(contract)
        assert avro["name"] == "orders"

    def test_namespace(self, contract):
        avro = to_avro_schema(contract)
        assert "datalasi" in avro["namespace"]

    def test_fields_list(self, contract):
        avro = to_avro_schema(contract)
        field_names = [f["name"] for f in avro["fields"]]
        assert set(field_names) == {"order_id", "amount", "status", "note", "quantity"}

    def test_int64_becomes_long(self, contract):
        avro = to_avro_schema(contract)
        order_id_field = next(f for f in avro["fields"] if f["name"] == "order_id")
        assert order_id_field["type"] == "long"

    def test_int32_becomes_int(self, contract):
        avro = to_avro_schema(contract)
        qty_field = next(f for f in avro["fields"] if f["name"] == "quantity")
        assert qty_field["type"] == "int"

    def test_float64_becomes_double(self, contract):
        avro = to_avro_schema(contract)
        amount_field = next(f for f in avro["fields"] if f["name"] == "amount")
        assert amount_field["type"] == "double"

    def test_enum_type(self, contract):
        avro = to_avro_schema(contract)
        status_field = next(f for f in avro["fields"] if f["name"] == "status")
        avro_type = status_field["type"]
        assert avro_type["type"] == "enum"
        assert set(avro_type["symbols"]) == {"PENDING", "COMPLETED", "CANCELLED"}

    def test_nullable_field_is_union(self, contract):
        avro = to_avro_schema(contract)
        note_field = next(f for f in avro["fields"] if f["name"] == "note")
        assert isinstance(note_field["type"], list)
        assert "null" in note_field["type"]

    def test_non_nullable_is_not_union(self, contract):
        avro = to_avro_schema(contract)
        id_field = next(f for f in avro["fields"] if f["name"] == "order_id")
        assert id_field["type"] == "long"

    def test_field_description_as_doc(self, contract):
        avro = to_avro_schema(contract)
        status_field = next(f for f in avro["fields"] if f["name"] == "status")
        assert status_field.get("doc") == "Order status"

    def test_date_logical_type(self):
        c = DataContract(
            name="t",
            version="1.0.0",
            schema={"dt": Field("dt", Date(), nullable=False)},
        )
        avro = to_avro_schema(c)
        dt_field = avro["fields"][0]
        assert dt_field["type"]["logicalType"] == "date"

    def test_timestamp_logical_type(self):
        c = DataContract(
            name="t",
            version="1.0.0",
            schema={"ts": Field("ts", Timestamp(), nullable=False)},
        )
        avro = to_avro_schema(c)
        ts_field = avro["fields"][0]
        assert ts_field["type"]["logicalType"] == "timestamp-millis"

    def test_convenience_method_on_contract(self, contract):
        assert contract.to_avro_schema() == to_avro_schema(contract)
