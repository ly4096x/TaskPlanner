"""Authentication and authorization — token generation, verification, permission checks."""

import base64
import hashlib
import secrets
import sqlite3
import time


def generate_token() -> tuple[str, str]:
    """Generate a new access token. Returns (raw_token, token_hash)."""
    raw_bytes = secrets.token_bytes(16)
    suffix = base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
    raw = f"tp_{suffix}"
    return raw, hash_token(raw)


def hash_token(raw_token: str) -> str:
    """SHA-256 hex hash of a raw token."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def verify_token(conn: sqlite3.Connection, raw_token: str) -> dict | None:
    """Verify a token and return the user dict (with role info), or None."""
    token_hash = hash_token(raw_token)
    row = conn.execute(
        """
        SELECT u.id, u.external_id, u.username, u.display_name,
               u.role, u.role_id, u.disabled, u.report_to, t.id as token_id,
               r.name as role_name
        FROM access_tokens t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE t.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()
    if row is None:
        return None
    user = dict(row)
    if user.get("disabled"):
        return None
    conn.execute(
        "UPDATE access_tokens SET last_used_time = ? WHERE id = ?",
        (time.time(), user.pop("token_id")),
    )
    conn.commit()
    if user.get("role_name"):
        user["role"] = user["role_name"]
    return user


# --- Permission checks ---


def is_admin(conn: sqlite3.Connection, role_id: int) -> bool:
    """Check if a role_id is the built-in admin role."""
    row = conn.execute(
        "SELECT 1 FROM roles WHERE id = ? AND name = 'admin' AND built_in = 1",
        (role_id,),
    ).fetchone()
    return row is not None


def check_board_action(conn: sqlite3.Connection, user: dict, board_id: int, action: str) -> bool:
    """Check if user can perform a per-board action (e.g. 'tasks.write' on board 3)."""
    role_id = user.get("role_id")
    if not role_id:
        return False
    if is_admin(conn, role_id):
        return True

    # Check board-specific override first
    board_rows = conn.execute(
        "SELECT action FROM role_permissions WHERE role_id = ? AND board_id = ?",
        (role_id, board_id),
    ).fetchall()

    if board_rows:
        # Override exists — use ONLY the board-specific permissions
        board_perms = {r[0] for r in board_rows}
        return action in board_perms

    # No override — fall back to defaults (board_id IS NULL)
    row = conn.execute(
        "SELECT 1 FROM role_permissions WHERE role_id = ? AND action = ? AND board_id IS NULL",
        (role_id, action),
    ).fetchone()
    return row is not None


def check_global_action(conn: sqlite3.Connection, user: dict, action: str) -> bool:
    """Check if user can perform a global action (e.g. 'users.manage', 'boards.create')."""
    role_id = user.get("role_id")
    if not role_id:
        return False
    if is_admin(conn, role_id):
        return True

    row = conn.execute(
        "SELECT 1 FROM role_permissions WHERE role_id = ? AND action = ? AND board_id IS NULL",
        (role_id, action),
    ).fetchone()
    return row is not None


# --- Backward compatibility wrappers (deprecated) ---


def has_permission(conn: sqlite3.Connection, user: dict, action: str) -> bool:
    """Check a global ACL action. Backward compat wrapper for check_global_action."""
    return check_global_action(conn, user, action)


def get_role_permissions(conn: sqlite3.Connection, role_id: int) -> set[str]:
    """Get default (non-board-specific) permissions for a role."""
    rows = conn.execute(
        "SELECT action FROM role_permissions WHERE role_id = ? AND board_id IS NULL",
        (role_id,),
    ).fetchall()
    return {row[0] for row in rows}


def check_permission(
    conn: sqlite3.Connection,
    user_id: int,
    role: str | None,
    board_id: int,
    required: str,
) -> bool:
    """Legacy wrapper. Maps 'read'→'boards.read', 'write'→'boards.write'."""
    user_row = conn.execute("SELECT role_id FROM users WHERE id = ?", (user_id,)).fetchone()
    role_id = user_row[0] if user_row else None
    user = {"id": user_id, "role_id": role_id}

    action = "boards.read" if required == "read" else "boards.write"
    return check_board_action(conn, user, board_id, action)
