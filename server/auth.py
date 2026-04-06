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
    """Verify a token and return the user dict (with role), or None if invalid/revoked/disabled."""
    token_hash = hash_token(raw_token)
    row = conn.execute(
        """
        SELECT u.id, u.external_id, u.username, u.display_name, u.role, u.disabled, u.report_to, t.id as token_id
        FROM access_tokens t
        JOIN users u ON t.user_id = u.id
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
    return user


def check_permission(
    conn: sqlite3.Connection,
    user_id: int,
    role: str | None,
    board_id: int,
    required: str,
) -> bool:
    """Check if a user has the required permission level on a board.

    required: 'read' or 'write'
    Returns True if allowed.
    """
    effective_role = role or "member"

    # Admin bypasses everything
    if effective_role == "admin":
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
            return True  # write implies read
        if perm == "read":
            return required == "read"

    # Fall back to role defaults
    if effective_role == "member":
        return True  # member can read + write
    if effective_role == "viewer":
        return required == "read"

    return False
