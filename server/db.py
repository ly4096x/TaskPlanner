"""SQLite connection management, schema initialization, WAL mode."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from server.schema import COMMENT_TYPES, STATUSES  # pyright: ignore[reportMissingImports]

# Current schema version
SCHEMA_VERSION = 19

GLOBAL_ACL_ACTIONS = frozenset({"boards.create", "users.manage", "users.create_direct_report", "users.edit"})
BOARD_ACL_ACTIONS = frozenset({
    "boards.read", "boards.write",
    "tasks.read", "tasks.create", "tasks.edit", "tasks.post_comment",
})
ACL_ACTIONS = GLOBAL_ACL_ACTIONS | BOARD_ACL_ACTIONS

_status_check = ", ".join(f"'{s}'" for s in STATUSES)
_comment_type_check = ", ".join(f"'{c}'" for c in COMMENT_TYPES)

_BASE_SCHEMA = f"""\
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
    report_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    role TEXT DEFAULT NULL,
    role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL,
    disabled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_time REAL NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
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
        CHECK (status IN ({_status_check})),
    parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    creator_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
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
        CHECK (comment_type IN ({_comment_type_check})),
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

CREATE TABLE IF NOT EXISTS access_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL DEFAULT '',
    created_time REAL NOT NULL,
    last_used_time REAL
);


CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    built_in INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    board_id INTEGER REFERENCES boards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_access_log (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    last_accessed_time REAL,
    PRIMARY KEY (user_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_comments_task_id ON comments(task_id);
CREATE INDEX IF NOT EXISTS idx_attachments_task_id ON attachments(task_id);
CREATE INDEX IF NOT EXISTS idx_attachments_comment_id ON attachments(comment_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_access_tokens_token_hash ON access_tokens(token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_perms_default ON role_permissions(role_id, action) WHERE board_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_perms_board ON role_permissions(role_id, action, board_id) WHERE board_id IS NOT NULL;
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_runtime_dir() -> Path:
    """Return the runtime data directory from TASKPLANNER_DATA_DIR env var.

    Set by TaskPlannerServer's data_dir argument, or directly via the env var.
    """
    env = os.environ.get("TASKPLANNER_DATA_DIR")
    if not env:
        raise RuntimeError(
            "TASKPLANNER_DATA_DIR not set. "
            "Use: TaskPlannerServer <data_dir>, or set TASKPLANNER_DATA_DIR."
        )
    d = Path(env).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_db_path() -> Path:
    """Return path to the DB file."""
    return get_runtime_dir() / "taskplanner.db"


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


def _migrate_to_v14(conn: sqlite3.Connection) -> None:
    """Add archived column to boards table."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(boards)").fetchall()}
    if "archived" not in cols:
        conn.execute(
            "ALTER TABLE boards ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def _migrate_to_v15(conn: sqlite3.Connection) -> None:
    """Add auth: role + disabled on users, access_tokens, board_permissions, task_access_log."""
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT NULL CHECK (role IN ('admin', 'member', 'viewer'))")
    if "disabled" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "access_tokens" not in tables:
        conn.executescript("""
            CREATE TABLE access_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                created_time REAL NOT NULL,
                last_used_time REAL
            );
            CREATE INDEX IF NOT EXISTS idx_access_tokens_token_hash ON access_tokens(token_hash);
        """)
    if "board_permissions" not in tables:
        conn.execute("""
            CREATE TABLE board_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
                permission TEXT NOT NULL CHECK (permission IN ('none', 'read', 'write')),
                UNIQUE (user_id, board_id)
            )
        """)
    if "task_access_log" not in tables:
        conn.execute("""
            CREATE TABLE task_access_log (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                last_accessed_time REAL,
                PRIMARY KEY (user_id, task_id)
            )
        """)
    # Migrate existing users to admin role
    conn.execute("UPDATE users SET role = 'admin' WHERE role IS NULL")
    conn.commit()


def _migrate_to_v16(conn: sqlite3.Connection) -> None:
    """Add custom roles system: roles table, role_permissions table, role_id on users."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    if "roles" not in tables:
        conn.executescript("""
            CREATE TABLE roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                built_in INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                board_id INTEGER REFERENCES boards(id) ON DELETE CASCADE
            );
        """)

    # Seed built-in roles
    for name, desc, perms in [
        ("admin", "Full access", ["boards.read", "boards.write", "tasks.read", "tasks.create", "tasks.edit", "users.manage"]),
        ("member", "Read and write tasks/boards", ["boards.read", "boards.write", "tasks.read", "tasks.create", "tasks.edit"]),
        ("viewer", "Read-only access", ["boards.read", "tasks.read"]),
    ]:
        conn.execute("INSERT OR IGNORE INTO roles (name, description, built_in) VALUES (?, ?, 1)", (name, desc))
        role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (name,)).fetchone()
        if role_row:
            for action in perms:
                conn.execute(
                    "INSERT OR IGNORE INTO role_permissions (role_id, action, board_id) VALUES (?, ?, NULL)",
                    (role_row[0], action),
                )

    # Add role_id column to users
    user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "role_id" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL")

    # Populate role_id from existing role text column
    conn.execute("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = users.role)
        WHERE role IS NOT NULL AND role_id IS NULL
    """)
    conn.execute("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'member')
        WHERE role_id IS NULL
    """)
    conn.commit()


def _migrate_to_v17(conn: sqlite3.Connection) -> None:
    """Per-board role permissions: add board_id to role_permissions, drop board_permissions."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    # Check if role_permissions already has board_id (fresh DB or already migrated)
    rp_cols = set()
    if "role_permissions" in tables:
        rp_cols = {row[1] for row in conn.execute("PRAGMA table_info(role_permissions)").fetchall()}

    needs_table_migration = "role_permissions" in tables and "board_id" not in rp_cols

    # 1. Rename old role_permissions (only if it needs migration)
    if needs_table_migration and "role_permissions_old" not in tables:
        conn.execute("ALTER TABLE role_permissions RENAME TO role_permissions_old")

    # 2. Create new table if needed
    if needs_table_migration:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                board_id INTEGER REFERENCES boards(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_role_perms_default
                ON role_permissions(role_id, action) WHERE board_id IS NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_role_perms_board
                ON role_permissions(role_id, action, board_id) WHERE board_id IS NOT NULL;
        """)

        # 3. Copy old rows as defaults
        conn.execute("""
            INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
            SELECT role_id, action, NULL FROM role_permissions_old
        """)

        # 4. Add boards.create to roles that had boards.write
        conn.execute("""
            INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
            SELECT role_id, 'boards.create', NULL FROM role_permissions
            WHERE action = 'boards.write' AND board_id IS NULL
        """)

    # 7. Drop old table
    conn.execute("DROP TABLE IF EXISTS role_permissions_old")

    # 5. Unassign users from member/viewer, then delete those roles
    # (role_permissions rows cascade-delete via FK)
    for role_name in ("member", "viewer"):
        role_row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
        if role_row:
            conn.execute("UPDATE users SET role_id = NULL WHERE role_id = ?", (role_row[0],))
            conn.execute("DELETE FROM roles WHERE id = ?", (role_row[0],))

    # 6. Drop board_permissions table
    conn.execute("DROP TABLE IF EXISTS board_permissions")

    conn.commit()


def _migrate_to_v18(conn: sqlite3.Connection) -> None:
    """Split tasks.write into tasks.create and tasks.edit (both default and per-board scope)."""
    # For every (role_id, board_id) that had tasks.write, insert tasks.create + tasks.edit.
    # IS NOT DISTINCT FROM treats NULL == NULL so default-scope rows match too.
    conn.execute("""
        INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
        SELECT role_id, 'tasks.create', board_id FROM role_permissions
        WHERE action = 'tasks.write'
    """)
    conn.execute("""
        INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
        SELECT role_id, 'tasks.edit', board_id FROM role_permissions
        WHERE action = 'tasks.write'
    """)
    # Also grant the new actions to anyone who has boards.write at the same scope,
    # since boards.write was the legacy gate enforced for task create/edit.
    conn.execute("""
        INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
        SELECT role_id, 'tasks.create', board_id FROM role_permissions
        WHERE action = 'boards.write'
    """)
    conn.execute("""
        INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
        SELECT role_id, 'tasks.edit', board_id FROM role_permissions
        WHERE action = 'boards.write'
    """)
    conn.execute("DELETE FROM role_permissions WHERE action = 'tasks.write'")
    conn.commit()


def _migrate_to_v19(conn: sqlite3.Connection) -> None:
    """Granular comment permission + task creator tracking.

    - Grant tasks.post_comment wherever a role has boards.write (at the same
      scope), since boards.write was the legacy gate for posting comments.
      Version-gated so an admin revoking tasks.post_comment from a role that
      keeps boards.write isn't silently re-granted on the next startup.
    - Add tasks.creator_id so the task creator can always comment on it.
      Existing rows stay NULL (the creating user was never recorded before
      v19), so the creator guarantee only applies to tasks created after
      the upgrade.
    """
    if _get_version(conn) < 19:
        conn.execute("""
            INSERT OR IGNORE INTO role_permissions (role_id, action, board_id)
            SELECT role_id, 'tasks.post_comment', board_id FROM role_permissions
            WHERE action = 'boards.write'
        """)
    task_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "creator_id" not in task_cols:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN creator_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        )
    conn.commit()


_MIGRATIONS = {
    12: _migrate_to_v12,
    13: _migrate_to_v13,
    14: _migrate_to_v14,
    15: _migrate_to_v15,
    16: _migrate_to_v16,
    17: _migrate_to_v17,
    18: _migrate_to_v18,
    19: _migrate_to_v19,
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
