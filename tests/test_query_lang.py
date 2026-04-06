"""Tests for filter parsing and template rendering."""

import pytest

from server.query_lang import (
    AndExpr,
    FilterClause,
    FilterParseError,
    NotExpr,
    OrExpr,
    TemplateParseError,
    parse_filter,
    parse_template,
    render,
    render_template,
    to_sql_where,
)

# ---------------------------------------------------------------------------
# Filter parsing tests
# ---------------------------------------------------------------------------


class TestParseFilter:
    def test_empty_filter(self):
        assert parse_filter("") is None

    def test_whitespace_only(self):
        assert parse_filter("   ") is None

    def test_simple_equality(self):
        result = parse_filter("STATUS=NEW")
        assert result == FilterClause("STATUS", "=", "NEW")

    def test_multiple_clauses_comma(self):
        result = parse_filter("STATUS=NEW,IMPORTANCE>=80")
        assert isinstance(result, AndExpr)
        assert result.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("IMPORTANCE", ">=", "80"),
        )

    def test_contains_operator(self):
        result = parse_filter("TITLE~=database")
        assert result == FilterClause("TITLE", "~=", "database")

    def test_not_equal(self):
        result = parse_filter("STATUS!=CANCELLED")
        assert result == FilterClause("STATUS", "!=", "CANCELLED")

    def test_less_than(self):
        result = parse_filter("IMPORTANCE<50")
        assert result == FilterClause("IMPORTANCE", "<", "50")

    def test_less_equal(self):
        result = parse_filter("IMPORTANCE<=50")
        assert result == FilterClause("IMPORTANCE", "<=", "50")

    def test_greater_than(self):
        result = parse_filter("IMPORTANCE>50")
        assert result == FilterClause("IMPORTANCE", ">", "50")

    def test_quoted_value_with_comma(self):
        result = parse_filter('TITLE~="hello, world"')
        assert result == FilterClause("TITLE", "~=", "hello, world")

    def test_escaped_quotes_in_value(self):
        result = parse_filter('DESCRIPTION~="say \\"hello\\""')
        assert result == FilterClause("DESCRIPTION", "~=", 'say "hello"')

    def test_quoted_value_multiple_clauses(self):
        result = parse_filter('TITLE~="hello, world",STATUS!=CANCELLED')
        assert isinstance(result, AndExpr)
        assert result.children == (
            FilterClause("TITLE", "~=", "hello, world"),
            FilterClause("STATUS", "!=", "CANCELLED"),
        )

    def test_invalid_field_raises_error(self):
        with pytest.raises(FilterParseError, match="Unknown field"):
            parse_filter("FOOBAR=123")

    def test_invalid_operator_raises_error(self):
        with pytest.raises(FilterParseError, match="Invalid operator"):
            parse_filter("STATUS??NEW")

    def test_tags_contains(self):
        result = parse_filter("TAGS~=backend")
        assert result == FilterClause("TAGS", "~=", "backend")

    def test_blockers_contains(self):
        result = parse_filter("BLOCKERS~=5")
        assert result == FilterClause("BLOCKERS", "~=", "5")


class TestParseFilterBoolean:
    """Tests for boolean logic: AND, OR, NOT, parentheses."""

    def test_and_keyword(self):
        result = parse_filter("STATUS=NEW AND IMPORTANCE>=50")
        assert isinstance(result, AndExpr)
        assert result.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("IMPORTANCE", ">=", "50"),
        )

    def test_or_keyword(self):
        result = parse_filter("STATUS=NEW OR STATUS=STARTED")
        assert isinstance(result, OrExpr)
        assert result.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("STATUS", "=", "STARTED"),
        )

    def test_not_keyword(self):
        result = parse_filter("NOT STATUS=CANCELLED")
        assert isinstance(result, NotExpr)
        assert result.child == FilterClause("STATUS", "=", "CANCELLED")

    def test_parenthesized_or_with_and(self):
        result = parse_filter("(STATUS=NEW OR STATUS=STARTED) AND IMPORTANCE>=80")
        assert isinstance(result, AndExpr)
        assert len(result.children) == 2
        or_part = result.children[0]
        assert isinstance(or_part, OrExpr)
        assert or_part.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("STATUS", "=", "STARTED"),
        )
        assert result.children[1] == FilterClause("IMPORTANCE", ">=", "80")

    def test_and_not(self):
        result = parse_filter("STATUS=NEW AND NOT TAGS~=test")
        assert isinstance(result, AndExpr)
        assert result.children[0] == FilterClause("STATUS", "=", "NEW")
        not_part = result.children[1]
        assert isinstance(not_part, NotExpr)
        assert not_part.child == FilterClause("TAGS", "~=", "test")

    def test_nested_not_with_parens(self):
        result = parse_filter("NOT (TITLE~=test AND STATUS=NEW)")
        assert isinstance(result, NotExpr)
        inner = result.child
        assert isinstance(inner, AndExpr)
        assert inner.children == (
            FilterClause("TITLE", "~=", "test"),
            FilterClause("STATUS", "=", "NEW"),
        )

    def test_comma_backward_compat(self):
        """Commas still work as implicit AND."""
        result = parse_filter("STATUS=NEW,IMPORTANCE>=50")
        assert isinstance(result, AndExpr)
        assert result.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("IMPORTANCE", ">=", "50"),
        )

    def test_mixed_comma_and_or(self):
        """Commas bind as AND, OR has lower precedence."""
        result = parse_filter("STATUS=NEW,IMPORTANCE>=50 OR TITLE~=urgent")
        assert isinstance(result, OrExpr)
        and_part = result.children[0]
        assert isinstance(and_part, AndExpr)
        assert and_part.children == (
            FilterClause("STATUS", "=", "NEW"),
            FilterClause("IMPORTANCE", ">=", "50"),
        )
        assert result.children[1] == FilterClause("TITLE", "~=", "urgent")

    def test_or_and_precedence(self):
        """AND binds tighter than OR: A OR B AND C -> OR(A, AND(B, C))."""
        result = parse_filter("TITLE~=bug OR TITLE~=fix AND STATUS!=DONE")
        assert isinstance(result, OrExpr)
        assert result.children[0] == FilterClause("TITLE", "~=", "bug")
        and_part = result.children[1]
        assert isinstance(and_part, AndExpr)
        assert and_part.children == (
            FilterClause("TITLE", "~=", "fix"),
            FilterClause("STATUS", "!=", "DONE"),
        )

    def test_complex_parens(self):
        result = parse_filter("(TITLE~=bug OR TITLE~=fix) AND STATUS!=DONE")
        assert isinstance(result, AndExpr)
        or_part = result.children[0]
        assert isinstance(or_part, OrExpr)
        assert or_part.children == (
            FilterClause("TITLE", "~=", "bug"),
            FilterClause("TITLE", "~=", "fix"),
        )
        assert result.children[1] == FilterClause("STATUS", "!=", "DONE")

    def test_invalid_syntax_double_and(self):
        with pytest.raises(FilterParseError):
            parse_filter("STATUS=NEW AND AND IMPORTANCE>=50")

    def test_invalid_syntax_trailing_or(self):
        with pytest.raises(FilterParseError):
            parse_filter("STATUS=NEW OR")

    def test_unmatched_paren(self):
        with pytest.raises(FilterParseError):
            parse_filter("(STATUS=NEW OR STATUS=STARTED")


# ---------------------------------------------------------------------------
# to_sql_where tests
# ---------------------------------------------------------------------------


class TestToSqlWhere:
    def test_none_input(self):
        sql, params = to_sql_where(None)
        assert sql == ""
        assert params == []

    def test_simple_equality(self):
        node = FilterClause("STATUS", "=", "NEW")
        sql, params = to_sql_where(node)
        assert "tasks.status = ?" in sql
        assert params == ["NEW"]

    def test_numeric_field_casts(self):
        node = FilterClause("IMPORTANCE", ">=", "80")
        sql, params = to_sql_where(node)
        assert "tasks.importance >= ?" in sql
        assert params == [80]

    def test_contains_on_string_field(self):
        node = FilterClause("TITLE", "~=", "database")
        sql, params = to_sql_where(node)
        assert "tasks.title LIKE ?" in sql
        assert params == ["%database%"]

    def test_tags_membership(self):
        node = FilterClause("TAGS", "~=", "backend")
        sql, params = to_sql_where(node)
        assert "tags.name" in sql
        assert params == ["backend"]

    def test_blockers_membership(self):
        node = FilterClause("BLOCKERS", "~=", "5")
        sql, params = to_sql_where(node)
        assert "task_dependencies" in sql
        assert params == [5]

    def test_assignee_join(self):
        node = FilterClause("ASSIGNEE", "=", "alice")
        sql, params = to_sql_where(node)
        assert "users" in sql
        assert "alice" in params

    def test_not_equal(self):
        node = FilterClause("STATUS", "!=", "CANCELLED")
        sql, params = to_sql_where(node)
        assert "tasks.status != ?" in sql
        assert params == ["CANCELLED"]

    def test_and_expr(self):
        node = AndExpr(
            children=(
                FilterClause("STATUS", "=", "NEW"),
                FilterClause("IMPORTANCE", ">=", "80"),
            )
        )
        sql, params = to_sql_where(node)
        assert " AND " in sql
        assert len(params) == 2

    def test_or_expr(self):
        node = OrExpr(
            children=(
                FilterClause("STATUS", "=", "NEW"),
                FilterClause("STATUS", "=", "STARTED"),
            )
        )
        sql, params = to_sql_where(node)
        assert " OR " in sql
        assert params == ["NEW", "STARTED"]

    def test_not_expr(self):
        node = NotExpr(child=FilterClause("STATUS", "=", "CANCELLED"))
        sql, params = to_sql_where(node)
        assert sql.startswith("NOT (")
        assert params == ["CANCELLED"]

    def test_not_tags_uses_not_exists(self):
        node = NotExpr(child=FilterClause("TAGS", "~=", "test"))
        sql, params = to_sql_where(node)
        assert "NOT EXISTS" in sql
        assert params == ["test"]

    def test_not_blockers_uses_not_exists(self):
        node = NotExpr(child=FilterClause("BLOCKERS", "~=", "5"))
        sql, params = to_sql_where(node)
        assert "NOT EXISTS" in sql
        assert params == [5]

    def test_complex_ast(self):
        """(STATUS=NEW OR STATUS=STARTED) AND IMPORTANCE>=80"""
        node = AndExpr(
            children=(
                OrExpr(
                    children=(
                        FilterClause("STATUS", "=", "NEW"),
                        FilterClause("STATUS", "=", "STARTED"),
                    )
                ),
                FilterClause("IMPORTANCE", ">=", "80"),
            )
        )
        sql, params = to_sql_where(node)
        assert " AND " in sql
        assert " OR " in sql
        assert len(params) == 3

    def test_parse_and_sql_roundtrip(self):
        """End-to-end: parse a boolean filter and convert to SQL."""
        node = parse_filter("(STATUS=NEW OR STATUS=STARTED) AND IMPORTANCE>=80")
        sql, params = to_sql_where(node)
        assert " AND " in sql
        assert " OR " in sql
        assert params == ["NEW", "STARTED", 80]


# ---------------------------------------------------------------------------
# Template parsing tests
# ---------------------------------------------------------------------------


class TestParseTemplate:
    def test_simple_field(self):
        parts = parse_template("{TITLE}")
        rendered = render_template(parts, {"TITLE": "My Task"})
        assert rendered == "My Task"

    def test_multiple_fields(self):
        result = render("{ID}: {TITLE}", {"ID": 1, "TITLE": "My Task"})
        assert result == "1: My Task"

    def test_conditional_with_content(self):
        result = render(
            "{?ASSIGNEE}assigned to {ASSIGNEE}{/ASSIGNEE}",
            {"ASSIGNEE": "alice"},
        )
        assert result == "assigned to alice"

    def test_conditional_empty_field(self):
        result = render(
            "{?ASSIGNEE}assigned to {ASSIGNEE}{/ASSIGNEE}",
            {"ASSIGNEE": None},
        )
        assert result == ""

    def test_conditional_empty_string(self):
        result = render(
            "{?ASSIGNEE}assigned to {ASSIGNEE}{/ASSIGNEE}",
            {"ASSIGNEE": ""},
        )
        assert result == ""

    def test_escaped_braces(self):
        result = render("{{literal}}", {"TITLE": "x"})
        assert result == "{literal}"

    def test_list_field_joining(self):
        result = render("{TAGS}", {"TAGS": ["backend", "urgent"]})
        assert result == "backend, urgent"

    def test_list_field_single(self):
        result = render("{TAGS}", {"TAGS": ["backend"]})
        assert result == "backend"

    def test_list_field_empty(self):
        result = render("{TAGS}", {"TAGS": []})
        assert result == ""

    def test_unknown_field_raises_error(self):
        with pytest.raises(TemplateParseError, match="Unknown field"):
            parse_template("{FOOBAR}")

    def test_nested_content_in_conditional(self):
        result = render(
            "{ID}: {TITLE}{?ASSIGNEE} (assigned to {ASSIGNEE}){/ASSIGNEE}",
            {"ID": 42, "TITLE": "Fix bug", "ASSIGNEE": "bob"},
        )
        assert result == "42: Fix bug (assigned to bob)"

    def test_nested_content_conditional_empty(self):
        result = render(
            "{ID}: {TITLE}{?ASSIGNEE} (assigned to {ASSIGNEE}){/ASSIGNEE}",
            {"ID": 42, "TITLE": "Fix bug", "ASSIGNEE": None},
        )
        assert result == "42: Fix bug"

    def test_literal_text_only(self):
        result = render("just text", {})
        assert result == "just text"

    def test_blockers_list(self):
        result = render("{BLOCKERS}", {"BLOCKERS": [1, 3, 5]})
        assert result == "1, 3, 5"

    def test_comments_field(self):
        result = render("{COMMENTS}", {"COMMENTS": "some notes"})
        assert result == "some notes"


# ---------------------------------------------------------------------------
# CREATED_TIME relative time filter tests
# ---------------------------------------------------------------------------


class TestCreatedTimeRelativeFilter:
    def test_absolute_timestamp_still_works(self):
        parsed = parse_filter("CREATED_TIME>=1234567890")
        sql, params = to_sql_where(parsed)
        assert "tasks.created_time >= ?" in sql
        assert params[0] == 1234567890

    def test_relative_negative_offset(self):
        import time

        parsed = parse_filter("CREATED_TIME>=-3600")
        sql, params = to_sql_where(parsed)
        assert "tasks.created_time >= ?" in sql
        expected = time.time() - 3600
        assert abs(params[0] - expected) < 5

    def test_relative_positive_zero(self):
        import time

        parsed = parse_filter("CREATED_TIME<=+0")
        sql, params = to_sql_where(parsed)
        assert "tasks.created_time <= ?" in sql
        expected = time.time()
        assert abs(params[0] - expected) < 5
