"""Shared schema loaded from shared/schema.yaml.

Single source of truth for statuses, transitions, comment types, event types,
and filter fields. Used by both Python (server + CLI) and TypeScript (web client).
"""

from pathlib import Path

import yaml

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "shared" / "schema.yaml"
_schema = yaml.safe_load(_SCHEMA_PATH.read_text())

# --- Statuses ---

STATUSES: list[str] = [s["id"] for s in _schema["statuses"]]
STATUS_LABELS: dict[str, str] = {s["id"]: s["label"] for s in _schema["statuses"]}
STATUS_CLI_COLORS: dict[str, str] = {s["id"]: s["cli_color"] for s in _schema["statuses"]}

# --- Transitions ---

TRANSITIONS: dict[str, list[str]] = _schema["transitions"]
TRANSITION_CONDITIONS: dict = _schema["transition_conditions"]


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Check if a status transition is allowed by the transition graph."""
    allowed = TRANSITIONS.get(from_status, [])
    return to_status in allowed


# --- Comment types ---

COMMENT_TYPES: list[str] = _schema["comment_types"]

# --- Event types ---

EVENT_TYPES: list[str] = _schema["event_types"]

# --- Filter fields ---

FILTER_FIELDS: list[dict] = _schema["filter_fields"]
VALID_FIELDS: frozenset[str] = frozenset(f["id"] for f in FILTER_FIELDS)
NUMERIC_FIELDS: frozenset[str] = frozenset(f["id"] for f in FILTER_FIELDS if f.get("numeric"))
LIST_FIELDS: frozenset[str] = frozenset(f["id"] for f in FILTER_FIELDS if f.get("list"))
