"""Unit tests for the structured ExpectationRule DSL."""

from __future__ import annotations

import pytest

from datalasi.core.expectations import ExpectationRule


class TestToExpression:
    def test_not_null(self):
        rule = ExpectationRule(column="amount", rule="not_null")
        assert "amount" in rule.to_expression()
        assert "isnull" in rule.to_expression()

    def test_gt(self):
        rule = ExpectationRule(column="amount", rule="gt", value=0)
        assert rule.to_expression() == "amount > 0"

    def test_gte(self):
        assert ExpectationRule("x", "gte", 5).to_expression() == "x >= 5"

    def test_lt(self):
        assert ExpectationRule("x", "lt", 100).to_expression() == "x < 100"

    def test_lte(self):
        assert ExpectationRule("x", "lte", 100).to_expression() == "x <= 100"

    def test_eq(self):
        assert ExpectationRule("status", "eq", "ACTIVE").to_expression() == "status == 'ACTIVE'"

    def test_ne(self):
        assert ExpectationRule("status", "ne", "DELETED").to_expression() == "status != 'DELETED'"

    def test_in(self):
        rule = ExpectationRule("status", "in", ["A", "B"])
        assert "isin" in rule.to_expression()

    def test_not_in(self):
        rule = ExpectationRule("status", "not_in", ["X"])
        assert "isin" in rule.to_expression()

    def test_regex(self):
        rule = ExpectationRule("email", "regex", r".*@.*")
        assert "str.match" in rule.to_expression()

    def test_between(self):
        rule = ExpectationRule("score", "between", [0, 100])
        expr = rule.to_expression()
        assert "score >= 0" in expr
        assert "score <= 100" in expr

    def test_unique(self):
        rule = ExpectationRule("id", "unique")
        assert "duplicated" in rule.to_expression()

    def test_unknown_rule_raises(self):
        rule = ExpectationRule(column="x", rule="gt", value=0)
        rule.rule = "nonexistent"  # type: ignore
        with pytest.raises(ValueError, match="Unknown rule type"):
            rule.to_expression()


class TestSerialization:
    def test_to_dict_minimal(self):
        rule = ExpectationRule(column="amount", rule="gt", value=0)
        d = rule.to_dict()
        assert d["column"] == "amount"
        assert d["rule"] == "gt"
        assert d["value"] == 0
        assert "description" not in d
        assert "severity" not in d

    def test_to_dict_full(self):
        rule = ExpectationRule(
            column="price",
            rule="gt",
            value=0,
            description="Price must be positive",
            severity="WARNING",
        )
        d = rule.to_dict()
        assert d["description"] == "Price must be positive"
        assert d["severity"] == "WARNING"

    def test_roundtrip(self):
        rule = ExpectationRule(
            column="score", rule="between", value=[0, 100], description="Score in range"
        )
        assert ExpectationRule.from_dict(rule.to_dict()) == rule

    def test_from_dict_defaults(self):
        rule = ExpectationRule.from_dict({"column": "x", "rule": "not_null"})
        assert rule.severity == "ERROR"
        assert rule.description is None
        assert rule.value is None


class TestStr:
    def test_str_uses_description(self):
        rule = ExpectationRule(column="x", rule="gt", value=0, description="Must be positive")
        assert str(rule) == "Must be positive"

    def test_str_fallback(self):
        rule = ExpectationRule(column="x", rule="gt", value=10)
        assert "x" in str(rule)
        assert "gt" in str(rule)


class TestPolarsExpr:
    def test_polars_gt(self):
        pytest.importorskip("polars")
        import polars as pl

        rule = ExpectationRule(column="amount", rule="gt", value=0)
        df = pl.DataFrame({"amount": [1.0, -1.0, 2.0]})
        mask = df.select(rule.to_polars_expr().alias("check"))["check"]
        assert mask.to_list() == [True, False, True]

    def test_polars_not_null(self):
        pytest.importorskip("polars")
        import polars as pl

        rule = ExpectationRule(column="x", rule="not_null")
        df = pl.DataFrame({"x": [1, None, 3]})
        mask = df.select(rule.to_polars_expr().alias("check"))["check"]
        assert mask.to_list() == [True, False, True]

    def test_polars_in(self):
        pytest.importorskip("polars")
        import polars as pl

        rule = ExpectationRule(column="s", rule="in", value=["A", "B"])
        df = pl.DataFrame({"s": ["A", "C", "B"]})
        mask = df.select(rule.to_polars_expr().alias("check"))["check"]
        assert mask.to_list() == [True, False, True]
