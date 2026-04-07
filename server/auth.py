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
    """Verify a token and return the user dict (with role info), or None if invalid/revoked/disabled."""
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
    # Update last_used_time
    conn.execute(
        "UPDATE access_tokens SET last_used_time = ? WHERE id = ?",
        (time.time(), user.pop("token_id")),
    )
    conn.commit()
    # Normalize role field for backward compat
    if user.get("role_name"):
        user["role"] = user["role_name"]
    return user


def get_role_permissions(conn: sqlite3.Connection, role_id: int) -> set[str]:
    """Get the set of ACL actions granted to a role."""
    rows = conn.execute(
        "SELECT action FROM role_permissions WHERE role_id = ?", (role_id,)
    ).fetchall()
    return {row[0] for row in rows}


def has_permission(conn: sqlite3.Connection, user: dict, action: str) -> bool:
    """Check if a user has a specific ACL action (global, ignoring board overrides)."""
    role_id = user.get("role_id")
    if role_id is None:
        return False
    # Admin role always has full access
    if user.get("role_name") == "admin" or user.get("role") == "admin":
        return True
    perms = get_role_permissions(conn, role_id)
    return action in perms


def check_permission(
    conn: sqlite3.Connection,
    user_id: int,
    role: str | None,
    board_id: int,
    required: str,
) -> bool:
    """Check if a user has the required permission level on a board.

    required: 'read' or 'write' (legacy interface)
    Maps to ACL actions: 'read' -> 'boards.read'/'tasks.read', 'write' -> 'boards.write'/'tasks.write'
    Returns True if allowed.
    """
    # Get role_id from user
    user_row = conn.execute("SELECT role_id FROM users WHERE id = ?", (user_id,)).fetchone()
    role_id = user_row[0] if user_row else None

    # If no role_id, default to member
    if role_id is None:
        member_row = conn.execute("SELECT id FROM roles WHERE name = 'member'").fetchone()
        role_id = member_row[0] if member_row else None

    # Check role name — admin bypasses everything
    if role_id:
        role_row = conn.execute("SELECT name FROM roles WHERE id = ?", (role_id,)).fetchone()
        if role_row and role_row[0] == "admin":
            return True

    # Check per-board override
    row = conn.execute(
        "SELECT permission FROM board_permissions WHERE user_id = ? AND board_id = ?",
        (user_id, board_id),
    ).fetchone()

    if row:
        perm = row[0]
        if perm == "none":
            return False
        if perm == "write":
            return True
        if perm == "read":
            return required == "read"

    # Fall back to role permissions
    if role_id:
        perms = get_role_permissions(conn, role_id)
        if required == "write":
            return "boards.write" in perms or "tasks.write" in perms
        if required == "read":
            return "boards.read" in perms or "tasks.read" in perms

    return False
