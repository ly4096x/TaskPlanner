"""SQLite connection management, schema initialization, WAL mode."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Current schema version
SCHEMA_VERSION = 13

_BASE_SCHEMA = """\
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    report_to INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_time REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE (board_id, name)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    description TEXT NOT NULL DEFAULT '',
    importance INTEGER NOT NULL DEFAULT 0 CHECK (importance >= 0 AND importance <= 100),
    estimated_effort INTEGER NOT NULL DEFAULT 0 CHECK (estimated_effort >= 0),
    created_time REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW','STARTED','BLOCKED','WAITING_FOR_COMMAND_EXECUTION','DONE','NOT_REPRODUCIBLE','CANCELLED')),
    parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    CHECK (parent_task_id != id)
);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    blockers INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, blockers),
    CHECK (task_id != blockers)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    commenter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    comment_type TEXT NOT NULL DEFAULT 'TEXT'
        CHECK (comment_type IN ('TEXT', 'METADATA_CHANGE', 'EXECUTION_LOG')),
    created_time REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    uploader_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_time REAL NOT NULL,
    comment_id INTEGER REFERENCES comments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_comments_task_id ON comments(task_id);
CREATE INDEX IF NOT EXISTS idx_attachments_task_id ON attachments(task_id);
CREATE INDEX IF NOT EXISTS idx_attachments_comment_id ON attachments(comment_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    """Return path to the DB file, located next to this module."""
    db_dir = Path(__file__).resolve().parent / "runtime_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "taskplanner.db"


@contextmanager
def get_connection(db_path: str | Path | None = None):
    """Context manager yielding a sqlite3.Connection with WAL mode and foreign keys ON."""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def _get_version(conn: sqlite3.Connection) -> int:
    """Get current schema version. Returns 0 for unversioned databases."""
    try:
        row = conn.execute("SELECT version FROM _schema_version").fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def _set_version(conn: sqlite3.Connection, version: int):
    """Set schema version."""
    conn.execute("DELETE FROM _schema_version")
    conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))
    conn.commit()


def _migrate_to_v12(conn: sqlite3.Connection) -> None:
    """Add comment_type column to comments table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "comment_type" not in cols:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN comment_type TEXT NOT NULL DEFAULT 'TEXT'"
        )
        conn.commit()


# Only keep the latest migration — old ones are deleted since the base schema
# already reflects the current version for fresh databases.
def _migrate_to_v13(conn: sqlite3.Connection) -> None:
    """Add report_to column to users table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "report_to" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN report_to INTEGER REFERENCES users(id) ON DELETE SET NULL"
        )
        conn.commit()


_MIGRATIONS = {
    12: _migrate_to_v12,
    13: _migrate_to_v13,
}


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist, run pending migrations."""
    conn.executescript(_BASE_SCHEMA)
    # Always run all migrations — they are idempotent (check before altering)
    for version in sorted(_MIGRATIONS):
        _MIGRATIONS[version](conn)
    current = _get_version(conn)
    if current < SCHEMA_VERSION:
        _set_version(conn, SCHEMA_VERSION)
