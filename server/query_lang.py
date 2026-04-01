"""Filter parser and template renderer for the TaskPlanner query language.

Filter language: parse --filter strings like "STATUS=NEW,IMPORTANCE>=80"
  Supports boolean logic: AND, OR, NOT, parentheses
Template language: parse --template strings like "{ID}: {TITLE} [{STATUS}]"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

# ---------------------------------------------------------------------------
# Valid fields
# ---------------------------------------------------------------------------

from server.schema import LIST_FIELDS, NUMERIC_FIELDS, VALID_FIELDS

# Fields available in templates (superset of filter fields)
TEMPLATE_FIELDS = VALID_FIELDS | {"COMMENTS", "PARENT_TITLE"}

OPERATORS = (">=", "<=", "!=", "~=", ">", "<", "=")

# Map from uppercase field name to SQL column expression
FIELD_TO_COLUMN = {
    "ID": "tasks.id",
    "TITLE": "tasks.title",
    "STATUS": "tasks.status",
    "DESCRIPTION": "tasks.description",
    "IMPORTANCE": "tasks.importance",
    "ESTIMATED_EFFORT": "tasks.estimated_effort",
    "CREATED_TIME": "tasks.created_time",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FilterParseError(ValueError):
    """Raised when a filter string cannot be parsed."""


class TemplateParseError(ValueError):
    """Raised when a template string cannot be parsed."""


# ---------------------------------------------------------------------------
# Filter language — AST nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilterClause:
    field: str
    op: str
    value: str


@dataclass(frozen=True)
class AndExpr:
    children: tuple  # tuple of FilterNode


@dataclass(frozen=True)
class OrExpr:
    children: tuple  # tuple of FilterNode


@dataclass(frozen=True)
class NotExpr:
    child: FilterClause | AndExpr | OrExpr | NotExpr  # FilterNode


# Type alias for any filter AST node
FilterNode = Union[FilterClause, AndExpr, OrExpr, NotExpr]


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize(filter_str: str) -> list[str]:
    """Tokenize a filter string into clauses, keywords, and parens.

    Tokens produced: clause strings (FIELD OP VALUE), 'AND', 'OR', 'NOT', '(', ')', ','
    """
    tokens: list[str] = []
    i = 0
    n = len(filter_str)

    while i < n:
        # Skip whitespace
        if filter_str[i] == " ":
            i += 1
            continue

        # Parentheses
        if filter_str[i] in "()":
            tokens.append(filter_str[i])
            i += 1
            continue

        # Comma (implicit AND)
        if filter_str[i] == ",":
            tokens.append(",")
            i += 1
            continue

        # Check for keywords AND, OR, NOT (word boundary required after)
        matched_keyword = False
        for keyword in ("AND", "OR", "NOT"):
            klen = len(keyword)
            if filter_str[i : i + klen].upper() == keyword:
                after = i + klen
                if after >= n or filter_str[after] in " (":
                    tokens.append(keyword)
                    i = after
                    matched_keyword = True
                    break
        if matched_keyword:
            continue

        # Consume a clause token: FIELD OP VALUE (may contain quoted strings)
        clause_start = i
        in_quotes = False
        while i < n:
            ch = filter_str[i]
            if ch == "\\" and in_quotes and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_quotes = not in_quotes
                i += 1
                continue
            if not in_quotes:
                if ch in ",()":
                    break
                if ch == " ":
                    # Peek ahead past spaces to see if next thing is keyword or close-paren
                    j = i
                    while j < n and filter_str[j] == " ":
                        j += 1
                    remainder = filter_str[j:]
                    if (
                        (
                            remainder[:3].upper() == "AND"
                            and (len(remainder) == 3 or remainder[3] in " (")
                        )
                        or (
                            remainder[:2].upper() == "OR"
                            and (len(remainder) == 2 or remainder[2] in " (")
                        )
                        or (
                            remainder[:3].upper() == "NOT"
                            and (len(remainder) == 3 or remainder[3] in " (")
                        )
                        or (j < n and filter_str[j] == ")")
                    ):
                        break
            i += 1
        token = filter_str[clause_start:i].strip()
        if token:
            tokens.append(token)

    return tokens


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------


class _Parser:
    """Recursive descent parser for boolean filter expressions.

    Grammar:
        expr     := or_expr
        or_expr  := and_expr ('OR' and_expr)*
        and_expr := not_expr (('AND' | ',') not_expr)*
        not_expr := 'NOT' not_expr | primary
        primary  := '(' expr ')' | clause
        clause   := FIELD OP VALUE
    """

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, expected: str) -> str:
        tok = self.peek()
        if tok != expected:
            raise FilterParseError(f"Expected {expected!r}, got {tok!r}")
        return self.consume()

    def parse(self) -> FilterNode:
        result = self._or_expr()
        if self.pos < len(self.tokens):
            raise FilterParseError(
                f"Unexpected token at position {self.pos}: {self.tokens[self.pos]!r}"
            )
        return result

    def _or_expr(self) -> FilterNode:
        children = [self._and_expr()]
        while self.peek() == "OR":
            self.consume()
            children.append(self._and_expr())
        if len(children) == 1:
            return children[0]
        return OrExpr(children=tuple(children))

    def _and_expr(self) -> FilterNode:
        children = [self._not_expr()]
        while self.peek() in ("AND", ","):
            self.consume()
            children.append(self._not_expr())
        if len(children) == 1:
            return children[0]
        return AndExpr(children=tuple(children))

    def _not_expr(self) -> FilterNode:
        if self.peek() == "NOT":
            self.consume()
            child = self._not_expr()
            return NotExpr(child=child)
        return self._primary()

    def _primary(self) -> FilterNode:
        if self.peek() == "(":
            self.consume()
            expr = self._or_expr()
            self.expect(")")
            return expr
        tok = self.peek()
        if tok is None:
            raise FilterParseError("Unexpected end of filter expression")
        if tok in ("AND", "OR", "NOT", ",", "(", ")"):
            raise FilterParseError(f"Unexpected token: {tok!r}")
        return self._clause()

    def _clause(self) -> FilterClause:
        tok = self.consume()
        return _parse_single_clause(tok)


# ---------------------------------------------------------------------------
# Single clause parsing helpers
# ---------------------------------------------------------------------------


def _parse_single_clause(clause_str: str) -> FilterClause:
    """Parse a single clause like 'STATUS=NEW' or 'TITLE~="hello, world"'."""
    clause_str = clause_str.strip()

    # Find operator
    found_op = None
    op_pos = -1
    for op in OPERATORS:
        pos = clause_str.find(op)
        if pos > 0:
            # Make sure we pick the earliest valid operator
            if (
                op_pos == -1
                or pos < op_pos
                or (pos == op_pos and found_op is not None and len(op) > len(found_op))
            ):
                # Check that the part before is all uppercase letters/underscores (a valid field)
                candidate_field = clause_str[:pos]
                if re.match(r"^[A-Z_]+$", candidate_field):
                    found_op = op
                    op_pos = pos

    if found_op is None:
        raise FilterParseError(f"Invalid operator in clause: {clause_str!r}")

    field = clause_str[:op_pos]
    raw_value = clause_str[op_pos + len(found_op) :]

    if field not in VALID_FIELDS:
        raise FilterParseError(f"Unknown field: {field!r}")

    # Unquote value
    value = _unquote_value(raw_value)

    return FilterClause(field=field, op=found_op, value=value)


def _unquote_value(raw: str) -> str:
    """Remove surrounding quotes and process escape sequences."""
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        inner = raw[1:-1]
        # Process escape sequences
        return inner.replace('\\"', '"')
    return raw


# ---------------------------------------------------------------------------
# Public API: parse_filter and to_sql_where
# ---------------------------------------------------------------------------


def parse_filter(filter_str: str) -> FilterNode | None:
    """Parse a filter string into an AST of filter nodes.

    Supports boolean expressions with AND, OR, NOT, and parentheses.
    Commas are treated as implicit AND for backward compatibility.

    Returns None for empty/whitespace-only input.

    Examples:
        parse_filter("STATUS=NEW,IMPORTANCE>=80")
        parse_filter("STATUS=NEW AND IMPORTANCE>=80")
        parse_filter("STATUS=NEW OR STATUS=STARTED")
        parse_filter("NOT STATUS=CANCELLED")
        parse_filter("(STATUS=NEW OR STATUS=STARTED) AND IMPORTANCE>=80")
    """
    filter_str = filter_str.strip()
    if not filter_str:
        return None

    tokens = _tokenize(filter_str)
    if not tokens:
        return None

    parser = _Parser(tokens)
    return parser.parse()


def to_sql_where(node: FilterNode | None) -> tuple[str, list]:
    """Convert a filter AST node to a SQL WHERE fragment and parameter list.

    Returns:
        (where_sql, params) where where_sql does NOT include the 'WHERE' keyword.
        Empty string and empty list if node is None.
    """
    if node is None:
        return "", []

    return _node_to_sql(node)


# ---------------------------------------------------------------------------
# AST to SQL conversion
# ---------------------------------------------------------------------------


def _node_to_sql(node: FilterNode) -> tuple[str, list]:
    """Recursively convert an AST node to SQL."""
    if isinstance(node, FilterClause):
        return _clause_to_sql(node)
    elif isinstance(node, AndExpr):
        parts = []
        params = []
        for child in node.children:
            sql, p = _node_to_sql(child)
            parts.append(sql)
            params.extend(p)
        return "(" + " AND ".join(parts) + ")", params
    elif isinstance(node, OrExpr):
        parts = []
        params = []
        for child in node.children:
            sql, p = _node_to_sql(child)
            parts.append(sql)
            params.extend(p)
        return "(" + " OR ".join(parts) + ")", params
    elif isinstance(node, NotExpr):
        child = node.child
        # Special handling for TAGS/BLOCKERS: use NOT EXISTS
        if isinstance(child, FilterClause) and child.field in LIST_FIELDS:
            return _clause_to_sql_negated(child)
        sql, params = _node_to_sql(child)
        return f"NOT ({sql})", params
    else:
        raise FilterParseError(f"Unknown AST node type: {type(node)}")


def _clause_to_sql(clause: FilterClause) -> tuple[str, list]:
    """Convert a single FilterClause to SQL condition and params."""
    field = clause.field
    op = clause.op
    value = clause.value

    # Handle TAGS field
    if field == "TAGS":
        if op == "~=":
            return (
                "EXISTS (SELECT 1 FROM task_tags JOIN tags ON task_tags.tag_id = tags.id "
                "WHERE task_tags.task_id = tasks.id AND tags.name = ?)",
                [value],
            )
        raise FilterParseError(f"Unsupported operator {op!r} for TAGS field")

    # Handle BLOCKERS field
    if field == "BLOCKERS":
        numeric_value = _cast_numeric(value, field)
        if op == "~=":
            return (
                "EXISTS (SELECT 1 FROM task_dependencies "
                "WHERE task_dependencies.task_id = tasks.id AND task_dependencies.blockers = ?)",
                [numeric_value],
            )
        raise FilterParseError(f"Unsupported operator {op!r} for BLOCKERS field")

    # Handle PARENT field
    if field == "PARENT":
        if value == "" and op == "=":
            return "tasks.parent_task_id IS NULL", []
        numeric_value = _cast_numeric(value, field)
        if op == "=":
            return "tasks.parent_task_id = ?", [numeric_value]
        sql_op = _op_to_sql(op)
        return f"tasks.parent_task_id {sql_op} ?", [numeric_value]

    # Handle ASSIGNEE field
    if field == "ASSIGNEE":
        # Empty value means unassigned
        if value == "" and op == "=":
            return "tasks.assignee_id IS NULL", []
        if value == "" and op == "!=":
            return "tasks.assignee_id IS NOT NULL", []
        sql_op = _op_to_sql(op)
        if op == "~=":
            return (
                "EXISTS (SELECT 1 FROM users "
                "WHERE users.id = tasks.assignee_id AND (users.username LIKE ? OR users.external_id LIKE ?))",
                [f"%{value}%", f"%{value}%"],
            )
        return (
            "EXISTS (SELECT 1 FROM users "
            "WHERE users.id = tasks.assignee_id AND (users.username {op} ? OR users.external_id {op} ?))".format(
                op=sql_op
            ),
            [value, value],
        )

    # Regular fields
    column = FIELD_TO_COLUMN.get(field)
    if column is None:
        raise FilterParseError(f"Unknown field: {field!r}")

    # Contains operator on string fields
    if op == "~=":
        return f"{column} LIKE ?", [f"%{value}%"]

    sql_op = _op_to_sql(op)

    # Cast numeric fields
    if field in NUMERIC_FIELDS:
        numeric_value = _cast_numeric(value, field)
        return f"{column} {sql_op} ?", [numeric_value]

    return f"{column} {sql_op} ?", [value]


def _clause_to_sql_negated(clause: FilterClause) -> tuple[str, list]:
    """Convert a TAGS/BLOCKERS FilterClause to a negated SQL condition (NOT EXISTS)."""
    field = clause.field
    op = clause.op
    value = clause.value

    if field == "TAGS":
        if op == "~=":
            return (
                "NOT EXISTS (SELECT 1 FROM task_tags JOIN tags ON task_tags.tag_id = tags.id "
                "WHERE task_tags.task_id = tasks.id AND tags.name = ?)",
                [value],
            )
        raise FilterParseError(f"Unsupported operator {op!r} for TAGS field")

    if field == "BLOCKERS":
        numeric_value = _cast_numeric(value, field)
        if op == "~=":
            return (
                "NOT EXISTS (SELECT 1 FROM task_dependencies "
                "WHERE task_dependencies.task_id = tasks.id AND task_dependencies.blockers = ?)",
                [numeric_value],
            )
        raise FilterParseError(f"Unsupported operator {op!r} for BLOCKERS field")

    raise FilterParseError(f"_clause_to_sql_negated called for non-list field: {field!r}")


def _op_to_sql(op: str) -> str:
    """Convert filter operator to SQL operator."""
    mapping = {
        "=": "=",
        "!=": "!=",
        ">": ">",
        "<": "<",
        ">=": ">=",
        "<=": "<=",
    }
    sql_op = mapping.get(op)
    if sql_op is None:
        raise FilterParseError(f"Cannot convert operator {op!r} to SQL")
    return sql_op


def _cast_numeric(value: str, field: str):
    """Cast a string value to int or float for numeric fields.

    For CREATED_TIME, values starting with + or - are relative to current time
    (in seconds).
    """
    try:
        if field == "CREATED_TIME" and value and value[0] in ("+", "-"):
            import time

            offset = float(value) if "." in value else int(value)
            return time.time() + offset
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        raise FilterParseError(f"Expected numeric value for {field}, got {value!r}")


# ---------------------------------------------------------------------------
# Template language
# ---------------------------------------------------------------------------


@dataclass
class TemplatePart:
    """A part of a parsed template."""

    kind: str  # "literal", "field", "conditional"
    value: str = ""  # literal text or field name
    children: list["TemplatePart"] | None = None  # for conditional blocks


def parse_template(template_str: str) -> list[TemplatePart]:
    """Parse a template string into a list of TemplatePart objects."""
    parts: list[TemplatePart] = []
    i = 0
    n = len(template_str)

    while i < n:
        ch = template_str[i]

        # Escaped braces
        if ch == "{" and i + 1 < n and template_str[i + 1] == "{":
            parts.append(TemplatePart(kind="literal", value="{"))
            i += 2
            continue
        if ch == "}" and i + 1 < n and template_str[i + 1] == "}":
            parts.append(TemplatePart(kind="literal", value="}"))
            i += 2
            continue

        # Opening brace: field ref or conditional
        if ch == "{":
            close = _find_matching_brace(template_str, i)
            if close == -1:
                raise TemplateParseError(f"Unmatched '{{' at position {i}")
            inner = template_str[i + 1 : close]

            # Conditional start: {?FIELD}
            if inner.startswith("?"):
                field_name = inner[1:]
                _validate_template_field(field_name)
                # Find the closing {/FIELD}
                closing_tag = "{/" + field_name + "}"
                # Search for closing tag after the opening tag
                search_start = close + 1
                close_pos = template_str.find(closing_tag, search_start)
                if close_pos == -1:
                    raise TemplateParseError(
                        f"Missing closing tag {{/{field_name}}} for conditional"
                    )
                # Parse the content between {?FIELD} and {/FIELD}
                body_str = template_str[close + 1 : close_pos]
                children = parse_template(body_str)
                parts.append(
                    TemplatePart(
                        kind="conditional",
                        value=field_name,
                        children=children,
                    )
                )
                i = close_pos + len(closing_tag)
                continue

            # Closing conditional tag should not appear at top level
            if inner.startswith("/"):
                raise TemplateParseError(
                    f"Unexpected closing tag {{/{inner[1:]}}} without matching conditional"
                )

            # Regular field reference
            _validate_template_field(inner)
            parts.append(TemplatePart(kind="field", value=inner))
            i = close + 1
            continue

        # Literal text: consume until next { or }
        lit_start = i
        while i < n and template_str[i] not in "{}":
            i += 1
        parts.append(TemplatePart(kind="literal", value=template_str[lit_start:i]))

    return parts


def _find_matching_brace(s: str, start: int) -> int:
    """Find the position of the closing '}' for an opening '{' at start."""
    # Simple: find next '}' that's not '}}' escape
    i = start + 1
    while i < len(s):
        if s[i] == "}":
            if i + 1 < len(s) and s[i + 1] == "}":
                i += 2
                continue
            return i
        i += 1
    return -1


def _validate_template_field(field_name: str) -> None:
    """Validate that a field name is known."""
    if field_name not in TEMPLATE_FIELDS:
        raise TemplateParseError(f"Unknown field: {field_name!r}")


def render_template(parts: list[TemplatePart], task: dict) -> str:
    """Render parsed template parts with task data."""
    result: list[str] = []

    for part in parts:
        if part.kind == "literal":
            result.append(part.value)
        elif part.kind == "field":
            value = task.get(part.value)
            result.append(_format_value(value))
        elif part.kind == "conditional":
            value = task.get(part.value)
            if _is_truthy(value):
                result.append(render_template(part.children or [], task))

    return "".join(result)


def _format_value(value) -> str:
    """Format a value for template output."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _is_truthy(value) -> bool:
    """Check if a value is truthy for conditional blocks."""
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


def render(template_str: str, task: dict) -> str:
    """Convenience function: parse and render a template in one call."""
    parts = parse_template(template_str)
    return render_template(parts, task)
