"""FastAPI application for TaskPlanner API."""

import asyncio
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from server import auth, crud, models
from server.db import get_connection, get_runtime_dir, init_db
from server.events import event_bus
from server.query_lang import FilterParseError, parse_filter, to_sql_where


def _get_upload_dir() -> Path:
    return get_runtime_dir() / "uploaded"


@asynccontextmanager
async def lifespan(app):
    _get_upload_dir().mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        init_db(conn)
    yield


app = FastAPI(title="TaskPlanner API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    with get_connection() as conn:
        yield conn


def _require_board(conn: sqlite3.Connection, board_id: int) -> dict:
    """Validate board exists; raise 404 if not."""
    board = crud.get_board(conn, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


# --- Auth dependencies ---


def get_current_user(
    request: Request, conn: sqlite3.Connection = Depends(get_db)
) -> dict | None:
    """Extract and verify token from Authorization header, X-Access-Token, or query param."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:]
    else:
        raw_token = request.headers.get("X-Access-Token")
    if not raw_token:
        raw_token = request.query_params.get("token")
    if not raw_token:
        return None
    return auth.verify_token(conn, raw_token)


def require_auth(user: dict | None = Depends(get_current_user)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if not auth.has_permission(conn, user, "users.manage"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_admin_or_member(user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if not auth.has_permission(conn, user, "boards.write"):
        raise HTTPException(status_code=403, detail="Admin or member access required")
    return user


def _check_board_read(conn: sqlite3.Connection, user: dict, board_id: int) -> None:
    _require_board(conn, board_id)
    if not auth.check_permission(conn, user["id"], user.get("role"), board_id, "read"):
        raise HTTPException(status_code=403, detail="Read access denied for this board")


def _check_board_write(conn: sqlite3.Connection, user: dict, board_id: int) -> None:
    _require_board(conn, board_id)
    if not auth.check_permission(conn, user["id"], user.get("role"), board_id, "write"):
        raise HTTPException(status_code=403, detail="Write access denied for this board")


def _check_board_action(conn: sqlite3.Connection, user: dict, board_id: int, action: str) -> None:
    _require_board(conn, board_id)
    if not auth.check_board_action(conn, user, board_id, action):
        raise HTTPException(status_code=403, detail=f"Action {action!r} not permitted on this board")


# Statuses that require a human-written comment when a non-admin transitions
# the task into them. NOT_REPRODUCIBLE additionally requires a specific prefix
# (enforced for everyone, not just non-admins).
_STATUS_COMMENT_REQUIRED = frozenset({
    "DONE", "WAITING_FOR_COMMAND_EXECUTION", "NOT_REPRODUCIBLE", "CANCELLED",
})


# --- Global ValueError handler ---


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return HTTPException(status_code=422, detail=str(exc))


# --- Auth routes ---


@app.get("/api/v1/auth/me", response_model=models.UserResponse)
def auth_me(user: dict = Depends(require_auth)):
    return user


# --- Token routes ---


@app.post("/api/v1/users/{user_id}/tokens", response_model=models.TokenResponse, status_code=201)
def create_token(
    user_id: int,
    body: models.TokenCreate,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    # Self or admin
    if user["id"] != user_id and (user.get("role") or "member") != "admin":
        raise HTTPException(status_code=403, detail="Can only create tokens for yourself or as admin")
    target = crud.get_user(conn, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    raw, token_hash = auth.generate_token()
    token = crud.create_access_token(conn, user_id, token_hash, label=body.label)
    token["token"] = raw
    return token


@app.get("/api/v1/users/{user_id}/tokens", response_model=list[models.TokenListResponse])
def list_tokens(
    user_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    if user["id"] != user_id and (user.get("role") or "member") != "admin":
        raise HTTPException(status_code=403, detail="Can only list tokens for yourself or as admin")
    return crud.list_access_tokens(conn, user_id)


@app.post("/api/v1/users/{user_id}/tokens/{token_id}/revoke")
def revoke_token(
    user_id: int,
    token_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    if user["id"] != user_id and (user.get("role") or "member") != "admin":
        raise HTTPException(status_code=403, detail="Can only revoke tokens for yourself or as admin")
    if not crud.revoke_access_token(conn, token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"ok": True}


# --- Role routes ---


@app.get("/api/v1/roles", response_model=list[models.RoleResponse])
def list_roles(user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db)):
    return crud.list_roles(conn)


@app.get("/api/v1/roles/{role_id}", response_model=models.RoleResponse)
def get_role(role_id: int, user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db)):
    role = crud.get_role(conn, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@app.post("/api/v1/roles", response_model=models.RoleResponse, status_code=201)
def create_role(
    body: models.RoleCreate,
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    from server.db import ACL_ACTIONS

    invalid = set(body.permissions) - ACL_ACTIONS
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid permissions: {invalid}")
    try:
        bp = [p.model_dump() for p in body.board_permissions] if body.board_permissions else None
        return crud.create_role(conn, body.name, body.description, body.permissions, bp)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/v1/roles/{role_id}", response_model=models.RoleResponse)
def update_role(
    role_id: int,
    body: models.RoleUpdate,
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    from server.db import ACL_ACTIONS

    if body.permissions is not None:
        invalid = set(body.permissions) - ACL_ACTIONS
        if invalid:
            raise HTTPException(status_code=422, detail=f"Invalid permissions: {invalid}")
    bp = [p.model_dump() for p in body.board_permissions] if body.board_permissions is not None else None
    try:
        result = crud.update_role(conn, role_id, body.name, body.description, body.permissions, bp)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return result


@app.delete("/api/v1/roles/{role_id}")
def delete_role(role_id: int, user: dict = Depends(require_admin), conn: sqlite3.Connection = Depends(get_db)):
    try:
        if not crud.delete_role(conn, role_id):
            raise HTTPException(status_code=404, detail="Role not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


# --- Board routes ---


@app.get("/api/v1/boards", response_model=list[models.BoardResponse])
def list_boards(
    include_archived: bool = Query(False),
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    return crud.list_boards(conn, include_archived=include_archived)


@app.post("/api/v1/boards/new", response_model=models.BoardResponse, status_code=201)
def create_board(
    board: models.BoardCreate,
    user: dict = Depends(require_admin_or_member),
    conn: sqlite3.Connection = Depends(get_db),
):
    return crud.create_board(conn, name=board.name, description=board.description)


@app.get("/api/v1/board/{board_id}", response_model=models.BoardResponse)
def get_board(
    board_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    return crud.get_board(conn, board_id)


@app.post("/api/v1/board/{board_id}/edit", response_model=models.BoardResponse)
def edit_board(
    board_id: int,
    update: models.BoardUpdate,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_write(conn, user, board_id)
    existing = crud.get_board(conn, board_id)
    fields = update.model_dump(exclude_none=True)
    if fields:
        return crud.update_board(conn, board_id, **fields)
    return existing


# --- SSE events ---


@app.get("/api/v1/board/{board_id}/events")
async def board_events(board_id: int, request: Request, user: dict | None = Depends(get_current_user)):
    """Server-Sent Events stream for real-time board updates."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    with get_connection() as conn:
        _check_board_read(conn, user, board_id)

    queue = event_bus.subscribe(board_id)

    async def stream():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(board_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/board/{board_id}/watch/stop")
def stop_watch(
    board_id: int,
    session_id: str | None = None,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    event_bus.publish(board_id, "watch_stop", {"session_id": session_id})
    return {"ok": True}


# --- Task routes (board-scoped) ---


@app.get("/api/v1/board/{board_id}/tasks", response_model=list[models.TaskResponse])
def list_tasks(
    board_id: int,
    filter: str | None = Query(None),
    sort: str | None = Query(None),
    limit: int | None = Query(None),
    offset: int | None = Query(None, alias="skip"),
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    where_clause = None
    if filter:
        # A malformed filter is a client error (400), not a server fault (500).
        try:
            parsed = parse_filter(filter)
            if parsed:
                where_sql, where_params = to_sql_where(parsed)
                where_clause = (where_sql, where_params)
        except FilterParseError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid filter: {exc}")
    return crud.list_tasks(
        conn, board_id=board_id, where_clause=where_clause, sort_by=sort, limit=limit, offset=offset
    )


@app.get("/api/v1/board/{board_id}/unread")
def get_unread_tasks(
    board_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return task IDs that have new TEXT comments or were created since user last viewed."""
    _check_board_read(conn, user, board_id)
    access_times = crud.get_task_access_times(conn, user["id"], board_id)
    comment_times = crud.get_latest_comment_times(conn, board_id, comment_type="TEXT")

    # Get all task IDs on this board
    all_task_ids = [
        row[0] for row in conn.execute("SELECT id FROM tasks WHERE board_id = ?", (board_id,)).fetchall()
    ]

    unread = []
    for task_id in all_task_ids:
        last_access = access_times.get(task_id)
        if last_access is None:
            # Never viewed — unread if it has TEXT comments or was created
            unread.append(task_id)
        else:
            # Check if new TEXT comment since last access
            latest_comment = comment_times.get(task_id)
            if latest_comment and latest_comment > last_access:
                unread.append(task_id)
    return unread


@app.post("/api/v1/board/{board_id}/mark-read")
def mark_tasks_read(
    board_id: int,
    body: dict,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Mark multiple tasks as read for the current user."""
    _check_board_read(conn, user, board_id)
    task_ids = body.get("task_ids", [])
    now = time.time()
    for tid in task_ids:
        crud.record_task_access(conn, user["id"], tid, now)
    return {"ok": True, "count": len(task_ids)}


@app.post("/api/v1/board/{board_id}/tasks/new", response_model=models.TaskResponse, status_code=201)
def create_task(
    board_id: int,
    task: models.TaskCreate,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_action(conn, user, board_id, "tasks.create")
    try:
        result = crud.create_task(
            conn,
            board_id=board_id,
            title=task.title,
            description=task.description,
            assignee_id=task.assignee_id,
            assignee=task.assignee,
            importance=task.importance,
            estimated_effort=task.estimated_effort,
            tags=task.tags,
            blockers=task.blockers,
            status=task.status,
            parent_task_id=task.parent_task_id,
            creator_id=user["id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    event_bus.publish(board_id, "task_created", result)
    return result


@app.get("/api/v1/board/{board_id}/tasks/{task_id}", response_model=models.TaskResponse)
def get_task(
    board_id: int,
    task_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # Log task access
    crud.record_task_access(conn, user["id"], task_id, time.time())
    return task


@app.post("/api/v1/board/{board_id}/tasks/{task_id}/edit", response_model=models.TaskResponse)
def edit_task(
    board_id: int,
    task_id: int,
    edit: models.TaskEdit,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_action(conn, user, board_id, "tasks.edit")
    existing = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Task not found")

    actor_id = user["id"]

    is_status_transition = (
        edit.status is not None and edit.status != existing["status"]
    )
    if is_status_transition and edit.status == "NOT_REPRODUCIBLE":
        if not edit.status_reason or not edit.status_reason.strip().startswith(
            "Not reproducible because:"
        ):
            raise HTTPException(
                status_code=422,
                detail='NOT_REPRODUCIBLE status requires status_reason starting with "Not reproducible because:"',
            )
    elif (
        is_status_transition
        and edit.status in _STATUS_COMMENT_REQUIRED
        and not auth.is_admin(conn, user.get("role_id") or 0)
    ):
        if not edit.status_reason or not edit.status_reason.strip():
            raise HTTPException(
                status_code=422,
                detail=f"Non-admin users must provide a status_reason comment when transitioning to {edit.status}",
            )

    if is_status_transition and edit.status_reason and edit.status_reason.strip():
        crud.add_comment(conn, task_id, edit.status_reason.strip(), commenter_id=actor_id)

    try:
        result = crud.edit_task_fields(
            conn,
            board_id=board_id,
            task_id=task_id,
            status=edit.status,
            assignee_id=edit.assignee_id if "assignee_id" in edit.model_fields_set else (None if "assignee" in edit.model_fields_set and edit.assignee is None else crud._UNSET),
            assignee=edit.assignee,
            title=edit.title,
            description=edit.description,
            importance=edit.importance,
            estimated_effort=edit.estimated_effort,
            tags=edit.tags,
            blockers=edit.blockers,
            parent_task_id=edit.parent_task_id if "parent_task_id" in edit.model_fields_set else crud._UNSET,
            actor_id=actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result:
        event_bus.publish(board_id, "task_updated", result)
    return result


# --- Comment routes (board-scoped) ---


@app.get(
    "/api/v1/board/{board_id}/tasks/{task_id}/comments",
    response_model=list[models.CommentResponse],
)
def get_task_comments(
    board_id: int,
    task_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return crud.get_comments(conn, task_id)


@app.post(
    "/api/v1/board/{board_id}/tasks/{task_id}/new_comment",
    response_model=models.CommentResponse,
    status_code=201,
)
def add_comment(
    board_id: int,
    task_id: int,
    comment: models.CommentCreate,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    # The task creator may always comment on their own task; everyone else
    # needs the granular tasks.post_comment action (not legacy boards.write).
    is_creator = task is not None and task.get("creator_id") == user["id"]
    if not is_creator:
        _check_board_action(conn, user, board_id, "tasks.post_comment")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    commenter_id = user["id"]
    if comment.as_user:
        if not auth.is_admin(conn, user.get("role_id") or 0):
            raise HTTPException(status_code=403, detail="Only admins may set as_user")
        resolved = crud.resolve_username(conn, comment.as_user)
        if resolved is None:
            raise HTTPException(status_code=400, detail=f"User {comment.as_user!r} not found")
        commenter_id = resolved
    result = crud.add_comment(
        conn, task_id, comment.content,
        commenter_id=commenter_id,
        comment_type=comment.comment_type,
    )
    event_bus.publish(board_id, "comment_added", {"task_id": task_id, "comment": result})
    return result


@app.get(
    "/api/v1/board/{board_id}/comments/{comment_id}",
    response_model=models.CommentResponse,
)
def get_comment(
    board_id: int,
    comment_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    comment = crud.get_comment(conn, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


# --- Tag routes (board-scoped) ---


@app.get("/api/v1/board/{board_id}/tags", response_model=list[models.TagResponse])
def list_tags(
    board_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    return crud.list_tags(conn, board_id=board_id)


# --- User routes (global) ---


@app.get("/api/v1/users", response_model=list[models.UserResponse])
def list_users(user: dict = Depends(require_auth), conn: sqlite3.Connection = Depends(get_db)):
    return crud.list_users(conn)


@app.post("/api/v1/users", response_model=models.UserResponse, status_code=201)
def create_user(
    body: models.UserCreate,
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    import sqlite3 as _sqlite3

    report_to_id = None
    if body.report_to:
        report_to_id = crud.resolve_username(conn, body.report_to)
        if report_to_id is None:
            raise HTTPException(status_code=404, detail=f"report_to user '{body.report_to}' not found")

    try:
        return crud.create_user(conn, body.external_id, body.display_name, username=body.username, report_to=report_to_id)
    except _sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"User with external_id '{body.external_id}' already exists"
        )


@app.get("/api/v1/users/{user_id}", response_model=models.UserResponse)
def get_user(
    user_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    target = crud.get_user(conn, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return target


@app.post("/api/v1/users/{user_id}", response_model=models.UserResponse)
def edit_user(
    user_id: int,
    user_update: models.UserUpdate,
    user: dict = Depends(require_admin),
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = crud.get_user(conn, user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="User not found")
    fields = user_update.model_dump(exclude_none=True)
    if "report_to" in fields:
        rt_username = fields["report_to"]
        rt_id = crud.resolve_username(conn, rt_username)
        if rt_id is None:
            raise HTTPException(status_code=404, detail=f"report_to user '{rt_username}' not found")
        fields["report_to"] = rt_id
    if fields:
        return crud.update_user(conn, user_id, **fields)
    return existing


# --- Attachment routes ---


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", name)
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_") or "file"


async def _handle_upload(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    file: UploadFile,
    uploader_id: int | None,
    comment_id: int | None = None,
) -> dict:
    original_name = file.filename or "unnamed"
    safe_name = f"{uuid4()}_{_safe_filename(original_name)}"
    content_type = file.content_type or ""

    file_path = _get_upload_dir() / safe_name
    content = await file.read()
    file_path.write_bytes(content)
    size = len(content)

    return crud.create_attachment(
        conn,
        board_id=board_id,
        task_id=task_id,
        filename=safe_name,
        original_name=original_name,
        content_type=content_type,
        size=size,
        uploader_id=uploader_id,
        comment_id=comment_id,
    )


@app.post(
    "/api/v1/board/{board_id}/tasks/{task_id}/upload",
    response_model=models.AttachmentResponse,
    status_code=201,
)
async def upload_file(
    board_id: int,
    task_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_write(conn, user, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return await _handle_upload(conn, board_id, task_id, file, uploader_id=user["id"])


@app.post(
    "/api/v1/board/{board_id}/tasks/{task_id}/comments/{comment_id}/upload",
    response_model=models.AttachmentResponse,
    status_code=201,
)
async def upload_comment_file(
    board_id: int,
    task_id: int,
    comment_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_write(conn, user, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    comment = crud.get_comment(conn, comment_id)
    if comment is None or comment["task_id"] != task_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    return await _handle_upload(conn, board_id, task_id, file, uploader_id=user["id"], comment_id=comment_id)


@app.get(
    "/api/v1/board/{board_id}/tasks/{task_id}/attachments",
    response_model=list[models.AttachmentResponse],
)
def list_attachments(
    board_id: int,
    task_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    _check_board_read(conn, user, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return crud.get_attachments(conn, task_id)


@app.get("/api/v1/files/{attachment_id}")
def serve_file(
    attachment_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    attachment = crud.get_attachment(conn, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = _get_upload_dir() / attachment["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=attachment["content_type"] or "application/octet-stream",
        filename=attachment["original_name"],
    )


@app.delete("/api/v1/files/{attachment_id}")
def delete_file(
    attachment_id: int,
    user: dict = Depends(require_auth),
    conn: sqlite3.Connection = Depends(get_db),
):
    attachment = crud.get_attachment(conn, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = _get_upload_dir() / attachment["filename"]
    if file_path.exists():
        file_path.unlink()

    crud.delete_attachment(conn, attachment_id)
    return {"ok": True}


# --- Static web client ---

_pkg_static = Path(__file__).resolve().parent / "static"
_dev_static = Path(__file__).resolve().parent.parent / "client_web" / "dist"
STATIC_DIR = _pkg_static if _pkg_static.is_dir() else _dev_static

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        static_file = STATIC_DIR / full_path
        if full_path and static_file.is_file() and STATIC_DIR in static_file.resolve().parents:
            return FileResponse(static_file)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        raise HTTPException(status_code=404, detail="Web client not found")
