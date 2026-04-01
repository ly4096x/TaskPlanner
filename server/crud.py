"""All DB read/write operations with auto-generated change-tracking comments."""

import sqlite3
import time
from typing import Any, cast


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Username resolution
# ---------------------------------------------------------------------------


def resolve_username(conn: sqlite3.Connection, username: str) -> int | None:
    """Resolve a username to a user ID. Returns None if not found."""
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def create_user(
    conn: sqlite3.Connection, external_id: str, display_name: str, username: str = "",
    report_to: int | None = None,
) -> dict:
    cur = conn.execute(
        "INSERT INTO users (external_id, username, display_name, report_to) VALUES (?, ?, ?, ?)",
        (external_id, username, display_name, report_to),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "external_id": external_id,
        "username": username,
        "display_name": display_name,
        "report_to": report_to,
    }


def get_user(conn: sqlite3.Connection, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def list_users(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def delete_user(conn: sqlite3.Connection, user_id: int) -> bool:
    cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return cur.rowcount > 0


_USER_UPDATE_WHITELIST = {"external_id", "username", "display_name", "report_to"}


def update_user(conn: sqlite3.Connection, user_id: int, **fields) -> dict | None:
    sets = []
    vals = []
    for k, v in fields.items():
        if v is not None and k in _USER_UPDATE_WHITELIST:
            sets.append(f"{k} = ?")
            vals.append(v)
    if sets:
        vals.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    return get_user(conn, user_id)


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


def create_board(conn: sqlite3.Connection, name: str, description: str = "") -> dict:
    created_time = time.time()
    cur = conn.execute(
        "INSERT INTO boards (name, description, created_time) VALUES (?, ?, ?)",
        (name, description, created_time),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "name": name,
        "description": description,
        "created_time": created_time,
        "archived": False,
    }


def get_board(conn: sqlite3.Connection, board_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    return _row_to_dict(row)


def list_boards(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict]:
    if include_archived:
        rows = conn.execute("SELECT * FROM boards ORDER BY id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM boards WHERE archived = 0 ORDER BY id").fetchall()
    return [dict(r) for r in rows]


_BOARD_UPDATE_WHITELIST = {"name", "description", "archived"}


def update_board(conn: sqlite3.Connection, board_id: int, **fields) -> dict | None:
    sets = []
    vals = []
    for k, v in fields.items():
        if v is not None and k in _BOARD_UPDATE_WHITELIST:
            sets.append(f"{k} = ?")
            vals.append(v)
    if sets:
        vals.append(board_id)
        conn.execute(f"UPDATE boards SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    return get_board(conn, board_id)


# ---------------------------------------------------------------------------
# Tags (board-scoped)
# ---------------------------------------------------------------------------


def create_tag(conn: sqlite3.Connection, board_id: int, name: str) -> dict:
    cur = conn.execute(
        "INSERT INTO tags (board_id, name) VALUES (?, ?)",
        (board_id, name),
    )
    conn.commit()
    return {"id": cur.lastrowid, "name": name}


def list_tags(conn: sqlite3.Connection, board_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tags WHERE board_id = ? ORDER BY id",
        (board_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_or_create_tag(conn: sqlite3.Connection, board_id: int, name: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM tags WHERE board_id = ? AND name = ?",
        (board_id, name),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO tags (board_id, name) VALUES (?, ?)",
        (board_id, name),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Tasks (board-scoped) — batch enrichment
# ---------------------------------------------------------------------------


def _enrich_tasks_batch(conn: sqlite3.Connection, tasks: list[dict]) -> list[dict]:
    """Batch-enrich tasks with tags, blockers, and assignee info (no N+1)."""
    if not tasks:
        return tasks

    task_ids = [t["id"] for t in tasks]
    placeholders = ",".join("?" * len(task_ids))

    # Tags
    tag_rows = conn.execute(
        f"SELECT tt.task_id, t.name FROM tags t JOIN task_tags tt ON t.id = tt.tag_id "
        f"WHERE tt.task_id IN ({placeholders}) ORDER BY t.name",
        task_ids,
    ).fetchall()
    tags_by_task: dict[int, list[str]] = {}
    for r in tag_rows:
        tags_by_task.setdefault(r[0], []).append(r[1])

    # Blockers
    dep_rows = conn.execute(
        f"SELECT task_id, blockers FROM task_dependencies "
        f"WHERE task_id IN ({placeholders}) ORDER BY blockers",
        task_ids,
    ).fetchall()
    blockers_by_task: dict[int, list[int]] = {}
    for r in dep_rows:
        blockers_by_task.setdefault(r[0], []).append(r[1])

    # Assignees (batch)
    assignee_ids = list({t["assignee_id"] for t in tasks if t.get("assignee_id")})
    assignee_map: dict[int, dict] = {}
    if assignee_ids:
        a_placeholders = ",".join("?" * len(assignee_ids))
        a_rows = conn.execute(
            f"SELECT id, display_name, username FROM users WHERE id IN ({a_placeholders})",
            assignee_ids,
        ).fetchall()
        for r in a_rows:
            assignee_map[r[0]] = {"display_name": r[1], "username": r[2]}

    for task in tasks:
        task["tags"] = tags_by_task.get(task["id"], [])
        task["blockers"] = blockers_by_task.get(task["id"], [])
        aid = task.get("assignee_id")
        if aid and aid in assignee_map:
            task["assignee_name"] = assignee_map[aid]["display_name"]
            task["assignee_username"] = assignee_map[aid]["username"]
        else:
            task["assignee_name"] = None
            task["assignee_username"] = None

    return tasks


def _enrich_task(conn: sqlite3.Connection, task: dict) -> dict:
    """Add tags, blockers, and assignee_name to a task dict."""
    return _enrich_tasks_batch(conn, [task])[0]


def _enrich_comments_batch(conn: sqlite3.Connection, comments: list[dict]) -> list[dict]:
    """Batch-enrich comments with commenter info."""
    if not comments:
        return comments

    commenter_ids = list({c["commenter_id"] for c in comments if c.get("commenter_id")})
    commenter_map: dict[int, dict] = {}
    if commenter_ids:
        placeholders = ",".join("?" * len(commenter_ids))
        rows = conn.execute(
            f"SELECT id, display_name, username FROM users WHERE id IN ({placeholders})",
            commenter_ids,
        ).fetchall()
        for r in rows:
            commenter_map[r[0]] = {"display_name": r[1], "username": r[2]}

    for comment in comments:
        cid = comment.get("commenter_id")
        if cid and cid in commenter_map:
            comment["commenter_name"] = commenter_map[cid]["display_name"]
            comment["commenter_username"] = commenter_map[cid]["username"]
        else:
            comment["commenter_name"] = None
            comment["commenter_username"] = None

    return comments


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


def create_task(
    conn: sqlite3.Connection,
    board_id: int,
    title: str,
    description: str = "",
    assignee_id: int | None = None,
    assignee: str | None = None,
    importance: int = 0,
    estimated_effort: int = 0,
    tags: list[str] | None = None,
    blockers: list[int] | None = None,
    status: str = "NEW",
    parent_task_id: int | None = None,
) -> dict:
    if tags is None:
        tags = []
    if blockers is None:
        blockers = []

    # Resolve assignee username to ID
    if assignee is not None and assignee_id is None:
        assignee_id = resolve_username(conn, assignee)
        if assignee_id is None:
            raise ValueError(f"User '{assignee}' not found")

    # Validate parent_task_id
    if parent_task_id is not None:
        parent = conn.execute(
            "SELECT board_id FROM tasks WHERE id = ?", (parent_task_id,)
        ).fetchone()
        if parent is None:
            raise ValueError(f"Parent task {parent_task_id} not found")
        if parent[0] != board_id:
            raise ValueError(f"Parent task {parent_task_id} is on a different board")

    created_time = time.time()
    cur = conn.execute(
        "INSERT INTO tasks (board_id, title, description, assignee_id, importance, "
        "estimated_effort, created_time, status, parent_task_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            board_id,
            title,
            description,
            assignee_id,
            importance,
            estimated_effort,
            created_time,
            status,
            parent_task_id,
        ),
    )
    task_id = cur.lastrowid

    # Tags (board-scoped)
    for tag_name in tags:
        tag_id = _get_or_create_tag(conn, board_id, tag_name)
        conn.execute(
            "INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (task_id, tag_id),
        )

    # Dependencies
    for dep_id in blockers:
        conn.execute(
            "INSERT INTO task_dependencies (task_id, blockers) VALUES (?, ?)",
            (task_id, dep_id),
        )

    conn.commit()
    assert task_id is not None
    return get_task(conn, board_id, task_id)  # type: ignore[return-value]


def get_task(conn: sqlite3.Connection, board_id: int, task_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND board_id = ?",
        (task_id, board_id),
    ).fetchone()
    if row is None:
        return None
    task = dict(row)
    return _enrich_task(conn, task)


def get_subtasks(conn: sqlite3.Connection, board_id: int, task_id: int) -> list[dict]:
    """Fetch direct children of a task."""
    rows = conn.execute(
        "SELECT * FROM tasks WHERE parent_task_id = ? AND board_id = ? ORDER BY id",
        (task_id, board_id),
    ).fetchall()
    tasks = [dict(r) for r in rows]
    return _enrich_tasks_batch(conn, tasks)


def list_tasks(
    conn: sqlite3.Connection,
    board_id: int,
    filters: list[dict] | None = None,
    where_clause: tuple[str, list] | None = None,
    sort_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict]:
    query = "SELECT DISTINCT tasks.* FROM tasks"
    joins = []
    wheres = ["tasks.board_id = ?"]
    params: list[Any] = [board_id]

    if filters:
        for f in filters:
            field = f["field"]
            op = f["op"]
            value = f["value"]

            if field == "tag":
                joins.append(
                    "JOIN task_tags tt_f ON tasks.id = tt_f.task_id JOIN tags t_f ON tt_f.tag_id = t_f.id"
                )
                wheres.append("t_f.name = ?")
                params.append(value)
            elif op == "contains":
                wheres.append(f"tasks.{field} LIKE ?")
                params.append(f"%{value}%")
            else:
                sql_op = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
                wheres.append(f"tasks.{field} {sql_op.get(op, '=')} ?")
                params.append(value)

    if where_clause:
        where_sql, where_params = where_clause
        if where_sql:
            wheres.append(where_sql)
            params.extend(where_params)

    if joins:
        query += " " + " ".join(joins)
    if wheres:
        query += " WHERE " + " AND ".join(wheres)

    sort_clauses = {
        "importance_desc": "tasks.importance DESC, tasks.id",
        "importance_asc": "tasks.importance ASC, tasks.id",
    }
    query += f" ORDER BY {sort_clauses.get(sort_by or '', 'tasks.id')}"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    if offset is not None:
        query += " OFFSET ?"
        params.append(offset)

    rows = conn.execute(query, params).fetchall()
    tasks = [dict(r) for r in rows]
    return _enrich_tasks_batch(conn, tasks)


def _add_change_comment(
    conn: sqlite3.Connection, task_id: int, content: str, actor_id: int | None = None
) -> None:
    conn.execute(
        "INSERT INTO comments (task_id, commenter_id, content, comment_type, created_time) VALUES (?, ?, ?, 'METADATA_CHANGE', ?)",
        (task_id, actor_id, content, time.time()),
    )


def update_task(
    conn: sqlite3.Connection, board_id: int, task_id: int, actor_id: int | None = None, **fields
) -> dict | None:
    current = get_task(conn, board_id, task_id)
    if not current:
        return None

    sets = []
    vals = []
    comment_lines = []

    for k, v in fields.items():
        old = current.get(k)
        if v is not None and old != v:
            sets.append(f"{k} = ?")
            vals.append(v)
            key = k.upper()
            if old is not None and old != "":
                comment_lines.append(f"-{key}={old}")
                comment_lines.append(f"+{key}={v}")
            else:
                comment_lines.append(f"+{key}={v}")

    if sets:
        vals.append(task_id)
        vals.append(board_id)
        conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ? AND board_id = ?",
            vals,
        )
        if comment_lines:
            _add_change_comment(conn, task_id, "\n".join(comment_lines), actor_id=actor_id)
        conn.commit()

    return get_task(conn, board_id, task_id)


_UNSET = object()


def _validate_status_transition(
    conn: sqlite3.Connection,
    current_task: dict,
    new_status: str,
    effective_assignee_id: int | None,
) -> None:
    """Validate a status transition, raising ValueError on invalid transitions."""
    from server.schema import TRANSITION_CONDITIONS, is_valid_transition

    current_status = current_task["status"]

    # Check transition graph
    if not is_valid_transition(current_status, new_status):
        raise ValueError(
            f"Cannot set status to {new_status} from {current_status}."
        )

    # Check assignee requirement
    exempt = TRANSITION_CONDITIONS.get("require_assignee_except", [])
    if new_status not in exempt and effective_assignee_id is None:
        raise ValueError(
            f"Cannot set status to {new_status} without an assignee. Assign the task first."
        )

    # Check per-status conditions
    conditions = TRANSITION_CONDITIONS.get(new_status, {})

    if conditions.get("require_blockers"):
        current_blockers = current_task.get("blockers", [])
        if not current_blockers:
            raise ValueError(
                "Cannot set status to BLOCKED without blockers. Add blockers first."
            )
        active_blockers = []
        for bid in current_blockers:
            blocker = conn.execute("SELECT status FROM tasks WHERE id = ?", (bid,)).fetchone()
            if blocker and blocker[0] not in ("DONE", "CANCELLED"):
                active_blockers.append(bid)
        if not active_blockers:
            raise ValueError(
                "Cannot set status to BLOCKED: all blockers are already DONE or CANCELLED."
            )


def _validate_parent_task_id(
    conn: sqlite3.Connection, board_id: int, task_id: int, parent_task_id: int
) -> None:
    """Validate parent_task_id: same board, no self-ref, no circular ancestry."""
    if parent_task_id == task_id:
        raise ValueError("A task cannot be its own parent")

    parent = conn.execute(
        "SELECT board_id FROM tasks WHERE id = ?", (parent_task_id,)
    ).fetchone()
    if parent is None:
        raise ValueError(f"Parent task {parent_task_id} not found")
    if parent[0] != board_id:
        raise ValueError(f"Parent task {parent_task_id} is on a different board")

    # Check for circular ancestry
    current = parent_task_id
    visited = {task_id}
    while current is not None:
        if current in visited:
            raise ValueError("Circular parent reference detected")
        visited.add(current)
        row = conn.execute("SELECT parent_task_id FROM tasks WHERE id = ?", (current,)).fetchone()
        current = row[0] if row else None


def edit_task_fields(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    *,
    status=None,
    assignee_id=_UNSET,
    assignee=None,
    title=None,
    description=None,
    importance=None,
    estimated_effort=None,
    tags=None,
    blockers=None,
    parent_task_id=_UNSET,
    actor_id=None,
) -> dict | None:
    """Unified task mutation: apply all field changes and post ONE combined comment."""
    current = get_task(conn, board_id, task_id)
    if not current:
        return None

    change_lines: list[str] = []

    # --- Resolve assignee username ---
    if assignee is not None and assignee_id is _UNSET:
        resolved = resolve_username(conn, assignee)
        if resolved is None:
            raise ValueError(f"User '{assignee}' not found")
        assignee_id = resolved

    # --- Assignee (process BEFORE status so status validation sees updated assignee) ---
    effective_assignee_id = current.get("assignee_id")
    if assignee_id is not _UNSET and assignee_id != current.get("assignee_id"):
        # Reject clearing assignee on non-NEW tasks (unless we're also setting status to NEW)
        if assignee_id is None and current.get("status") != "NEW" and status != "NEW":
            raise ValueError("Cannot unassign a task that is not in NEW status.")
        conn.execute(
            "UPDATE tasks SET assignee_id = ? WHERE id = ? AND board_id = ?",
            (assignee_id, task_id, board_id),
        )
        old_assignee = current.get("assignee_username") or ""
        if assignee_id is not None:
            user = get_user(conn, cast(int, assignee_id))
            new_name = user["username"] if user else ""
            parts = [f"+{new_name}"]
            if old_assignee:
                parts.append(f"-{old_assignee}")
            change_lines.append(f"ASSIGNEE={','.join(parts)}")
        else:
            parts = []
            if old_assignee:
                parts.append(f"-{old_assignee}")
            change_lines.append(f"ASSIGNEE={','.join(parts)}")
        effective_assignee_id = assignee_id

    # --- Status ---
    if status is not None and status != current["status"]:
        _validate_status_transition(
            conn, current, status, cast(int | None, effective_assignee_id)
        )

        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ? AND board_id = ?",
            (status, task_id, board_id),
        )
        old_status = current["status"]
        parts = [f"+{status}"]
        if old_status:
            parts.append(f"-{old_status}")
        change_lines.append(f"STATUS={','.join(parts)}")

    # --- Parent task ---
    if parent_task_id is not _UNSET and parent_task_id != current.get("parent_task_id"):
        if parent_task_id is not None and parent_task_id != 0:
            _validate_parent_task_id(conn, board_id, task_id, cast(int, parent_task_id))
        else:
            parent_task_id = None
        conn.execute(
            "UPDATE tasks SET parent_task_id = ? WHERE id = ? AND board_id = ?",
            (parent_task_id, task_id, board_id),
        )
        old_parent = current.get("parent_task_id")
        parts = []
        if parent_task_id:
            parts.append(f"+{parent_task_id}")
        if old_parent:
            parts.append(f"-{old_parent}")
        change_lines.append(f"PARENT={','.join(parts)}")

    # --- Generic fields (title, description, importance, estimated_effort) ---
    generic_updates = {}
    for field_name, new_val in [
        ("title", title),
        ("description", description),
        ("importance", importance),
        ("estimated_effort", estimated_effort),
    ]:
        if new_val is not None:
            old_val = current.get(field_name)
            if old_val != new_val:
                generic_updates[field_name] = new_val
                key = field_name.upper()
                parts = [f"+{new_val}"]
                if old_val is not None and old_val != "":
                    parts.append(f"-{old_val}")
                change_lines.append(f"{key}={','.join(parts)}")

    if generic_updates:
        sets = [f"{k} = ?" for k in generic_updates]
        vals = list(generic_updates.values()) + [task_id, board_id]
        conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ? AND board_id = ?",
            vals,
        )

    # --- Tags ---
    if tags is not None:
        current_tag_rows = conn.execute(
            "SELECT t.name FROM tags t JOIN task_tags tt ON t.id = tt.tag_id WHERE tt.task_id = ?",
            (task_id,),
        ).fetchall()
        current_tags = set(r[0] for r in current_tag_rows)
        new_tags = set(tags)

        added = new_tags - current_tags
        removed = current_tags - new_tags

        if added or removed:
            conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
            for tag_name in tags:
                tag_id = _get_or_create_tag(conn, board_id, tag_name)
                conn.execute(
                    "INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)",
                    (task_id, tag_id),
                )
            for t in sorted(added):
                change_lines.append(f"TAGS+={t}")
            for t in sorted(removed):
                change_lines.append(f"TAGS-={t}")

    # --- Blockers ---
    if blockers is not None:
        # Validate same-board
        for dep_id in blockers:
            row = conn.execute("SELECT board_id FROM tasks WHERE id = ?", (dep_id,)).fetchone()
            if row is None or row[0] != board_id:
                raise ValueError(
                    f"cross-board dependency rejected: task {dep_id} does not belong to board {board_id}"
                )

        current_blocker_rows = conn.execute(
            "SELECT blockers FROM task_dependencies WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        current_blockers_set = set(r[0] for r in current_blocker_rows)
        new_blockers = set(blockers)

        added = new_blockers - current_blockers_set
        removed = current_blockers_set - new_blockers

        if added or removed:
            conn.execute("DELETE FROM task_dependencies WHERE task_id = ?", (task_id,))
            for dep_id in blockers:
                conn.execute(
                    "INSERT INTO task_dependencies (task_id, blockers) VALUES (?, ?)",
                    (task_id, dep_id),
                )
            for t in sorted(added):
                change_lines.append(f"BLOCKERS+={t}")
            for t in sorted(removed):
                change_lines.append(f"BLOCKERS-={t}")

    # --- Post ONE combined comment ---
    if change_lines:
        _add_change_comment(conn, task_id, "\n".join(change_lines), actor_id=actor_id)

    conn.commit()
    return get_task(conn, board_id, task_id)


def set_task_status(
    conn: sqlite3.Connection, board_id: int, task_id: int, status: str, actor_id: int | None = None
) -> dict | None:
    current = get_task(conn, board_id, task_id)
    if current and current["status"] == status:
        return current

    if current:
        _validate_status_transition(conn, current, status, current.get("assignee_id"))

    conn.execute(
        "UPDATE tasks SET status = ? WHERE id = ? AND board_id = ?",
        (status, task_id, board_id),
    )
    old_status = current["status"] if current else None
    parts = [f"+{status}"]
    if old_status:
        parts.append(f"-{old_status}")
    _add_change_comment(conn, task_id, f"STATUS={','.join(parts)}", actor_id=actor_id)
    conn.commit()
    return get_task(conn, board_id, task_id)


def assign_task(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    user_id: int | None,
    actor_id: int | None = None,
) -> dict | None:
    current = get_task(conn, board_id, task_id)
    if current and current.get("assignee_id") == user_id:
        return current
    # Reject clearing assignee on non-NEW tasks
    if user_id is None and current and current.get("status") != "NEW":
        raise ValueError("Cannot unassign a task that is not in NEW status.")
    conn.execute(
        "UPDATE tasks SET assignee_id = ? WHERE id = ? AND board_id = ?",
        (user_id, task_id, board_id),
    )
    old_assignee = current.get("assignee_username") or "" if current else ""
    if user_id is not None:
        user = get_user(conn, user_id)
        new_name = user["username"] if user else ""
        parts = [f"+{new_name}"]
        if old_assignee:
            parts.append(f"-{old_assignee}")
        _add_change_comment(conn, task_id, f"ASSIGNEE={','.join(parts)}", actor_id=actor_id)
    else:
        parts = []
        if old_assignee:
            parts.append(f"-{old_assignee}")
        _add_change_comment(conn, task_id, f"ASSIGNEE={','.join(parts)}", actor_id=actor_id)
    conn.commit()
    return get_task(conn, board_id, task_id)


def set_task_tags(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    tags: list[str],
    actor_id: int | None = None,
) -> dict | None:
    # Get current tags
    current_rows = conn.execute(
        "SELECT t.name FROM tags t JOIN task_tags tt ON t.id = tt.tag_id WHERE tt.task_id = ?",
        (task_id,),
    ).fetchall()
    current_tags = set(r[0] for r in current_rows)
    new_tags = set(tags)

    added = new_tags - current_tags
    removed = current_tags - new_tags

    # Clear all and re-insert
    conn.execute("DELETE FROM task_tags WHERE task_id = ?", (task_id,))
    for tag_name in tags:
        tag_id = _get_or_create_tag(conn, board_id, tag_name)
        conn.execute(
            "INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)",
            (task_id, tag_id),
        )

    # Generate comments
    comment_parts = []
    for t in sorted(added):
        comment_parts.append(f"TAGS+={t}")
    for t in sorted(removed):
        comment_parts.append(f"TAGS-={t}")
    if comment_parts:
        _add_change_comment(conn, task_id, "\n".join(comment_parts), actor_id=actor_id)

    conn.commit()
    return get_task(conn, board_id, task_id)


def set_task_blockers(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    task_ids: list[int],
    actor_id: int | None = None,
) -> dict | None:
    # Validate all referenced tasks belong to the same board
    for dep_id in task_ids:
        row = conn.execute("SELECT board_id FROM tasks WHERE id = ?", (dep_id,)).fetchone()
        if row is None or row[0] != board_id:
            raise ValueError(
                f"cross-board dependency rejected: task {dep_id} does not belong to board {board_id}"
            )

    # Get current blockers
    current_rows = conn.execute(
        "SELECT blockers FROM task_dependencies WHERE task_id = ?",
        (task_id,),
    ).fetchall()
    current = set(r[0] for r in current_rows)
    new = set(task_ids)

    added = new - current
    removed = current - new

    # Clear and re-insert
    conn.execute("DELETE FROM task_dependencies WHERE task_id = ?", (task_id,))
    for dep_id in task_ids:
        conn.execute(
            "INSERT INTO task_dependencies (task_id, blockers) VALUES (?, ?)",
            (task_id, dep_id),
        )

    # Generate comments
    comment_parts = []
    for t in sorted(added):
        comment_parts.append(f"BLOCKERS+={t}")
    for t in sorted(removed):
        comment_parts.append(f"BLOCKERS-={t}")
    if comment_parts:
        _add_change_comment(conn, task_id, "\n".join(comment_parts), actor_id=actor_id)

    conn.commit()
    return get_task(conn, board_id, task_id)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def add_comment(
    conn: sqlite3.Connection,
    task_id: int,
    content: str,
    commenter_id: int | None = None,
    commenter: str | None = None,
    comment_type: str = "TEXT",
) -> dict:
    # Resolve commenter username
    if commenter is not None and commenter_id is None:
        commenter_id = resolve_username(conn, commenter)

    created_time = time.time()
    cur = conn.execute(
        "INSERT INTO comments (task_id, commenter_id, content, comment_type, created_time) VALUES (?, ?, ?, ?, ?)",
        (task_id, commenter_id, content, comment_type, created_time),
    )
    conn.commit()
    comment = {
        "id": cur.lastrowid,
        "task_id": task_id,
        "commenter_id": commenter_id,
        "content": content,
        "comment_type": comment_type,
        "created_time": created_time,
    }
    return _enrich_comments_batch(conn, [comment])[0]


def _enrich_comment(conn: sqlite3.Connection, comment: dict) -> dict:
    """Add commenter_name and commenter_username to comment dict."""
    return _enrich_comments_batch(conn, [comment])[0]


def get_comments(conn: sqlite3.Connection, task_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM comments WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    comments = [dict(r) for r in rows]
    return _enrich_comments_batch(conn, comments)


def get_comment(conn: sqlite3.Connection, comment_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if row is None:
        return None
    return _enrich_comment(conn, dict(row))


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def create_attachment(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    filename: str,
    original_name: str,
    content_type: str = "",
    size: int = 0,
    uploader_id: int | None = None,
    comment_id: int | None = None,
) -> dict:
    created_time = time.time()
    cur = conn.execute(
        "INSERT INTO attachments (task_id, board_id, filename, original_name, content_type, size, uploader_id, created_time, comment_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, board_id, filename, original_name, content_type, size, uploader_id, created_time, comment_id),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "task_id": task_id,
        "board_id": board_id,
        "filename": filename,
        "original_name": original_name,
        "content_type": content_type,
        "size": size,
        "uploader_id": uploader_id,
        "created_time": created_time,
        "comment_id": comment_id,
    }


def get_attachments(conn: sqlite3.Connection, task_id: int) -> list[dict]:
    """Fetch task-level attachments only (excludes comment attachments)."""
    rows = conn.execute(
        "SELECT * FROM attachments WHERE task_id = ? AND comment_id IS NULL ORDER BY id",
        (task_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attachments_for_comment(conn: sqlite3.Connection, comment_id: int) -> list[dict]:
    """Fetch attachments for a specific comment."""
    rows = conn.execute(
        "SELECT * FROM attachments WHERE comment_id = ? ORDER BY id",
        (comment_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attachment(conn: sqlite3.Connection, attachment_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    return _row_to_dict(row)


def delete_attachment(conn: sqlite3.Connection, attachment_id: int) -> bool:
    cur = conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    return cur.rowcount > 0
