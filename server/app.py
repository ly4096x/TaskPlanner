"""FastAPI application for TaskPlanner API."""

import asyncio
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from server import crud, models
from server.db import get_connection, get_runtime_dir, init_db
from server.events import event_bus
from server.query_lang import parse_filter, to_sql_where

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


def _resolve_actor(conn: sqlite3.Connection, request: Request) -> int | None:
    """Resolve actor from X-Actor-Username header."""
    actor_username = request.headers.get("X-Actor-Username")
    if actor_username:
        return crud.resolve_username(conn, actor_username)
    return None


# --- Global ValueError handler ---


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return HTTPException(status_code=422, detail=str(exc))


# --- Board routes ---


@app.get("/api/v1/boards", response_model=list[models.BoardResponse])
def list_boards(
    include_archived: bool = Query(False),
    conn: sqlite3.Connection = Depends(get_db),
):
    return crud.list_boards(conn, include_archived=include_archived)


@app.post("/api/v1/boards/new", response_model=models.BoardResponse, status_code=201)
def create_board(
    board: models.BoardCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    return crud.create_board(conn, name=board.name, description=board.description)


@app.get("/api/v1/board/{board_id}", response_model=models.BoardResponse)
def get_board(
    board_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    board = crud.get_board(conn, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


@app.post("/api/v1/board/{board_id}/edit", response_model=models.BoardResponse)
def edit_board(
    board_id: int,
    update: models.BoardUpdate,
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = crud.get_board(conn, board_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Board not found")
    fields = update.model_dump(exclude_none=True)
    if fields:
        return crud.update_board(conn, board_id, **fields)
    return existing


# --- SSE events ---


@app.get("/api/v1/board/{board_id}/events")
async def board_events(board_id: int, request: Request):
    """Server-Sent Events stream for real-time board updates."""
    with get_connection() as conn:
        _require_board(conn, board_id)

    queue = event_bus.subscribe(board_id)

    async def stream():
        try:
            # Send keepalive comment on connect
            yield ": connected\n\n"
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment every 30s
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(board_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/board/{board_id}/watch/stop")
def stop_watch(
    board_id: int,
    session_id: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Publish a watch_stop event so any watcher on this board exits cleanly."""
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
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    where_clause = None
    if filter:
        parsed = parse_filter(filter)
        if parsed:
            where_sql, where_params = to_sql_where(parsed)
            where_clause = (where_sql, where_params)
    return crud.list_tasks(
        conn, board_id=board_id, where_clause=where_clause, sort_by=sort, limit=limit, offset=offset
    )


@app.post("/api/v1/board/{board_id}/tasks/new", response_model=models.TaskResponse, status_code=201)
def create_task(
    board_id: int,
    task: models.TaskCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
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
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    event_bus.publish(board_id, "task_created", result)
    return result


@app.get("/api/v1/board/{board_id}/tasks/{task_id}", response_model=models.TaskResponse)
def get_task(
    board_id: int,
    task_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/api/v1/board/{board_id}/tasks/{task_id}/edit", response_model=models.TaskResponse)
def edit_task(
    board_id: int,
    task_id: int,
    edit: models.TaskEdit,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    existing = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Task not found")

    actor_id = _resolve_actor(conn, request)

    # NOT_REPRODUCIBLE status_reason validation (before unified edit)
    if edit.status is not None and edit.status == "NOT_REPRODUCIBLE":
        if not edit.status_reason or not edit.status_reason.strip().startswith(
            "Not reproducible because:"
        ):
            raise HTTPException(
                status_code=422,
                detail='NOT_REPRODUCIBLE status requires status_reason starting with "Not reproducible because:"',
            )
        crud.add_comment(conn, task_id, edit.status_reason.strip())

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
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
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
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    result = crud.add_comment(
        conn, task_id, comment.content,
        commenter_id=comment.commenter_id,
        commenter=comment.commenter,
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
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    comment = crud.get_comment(conn, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


# --- Tag routes (board-scoped) ---


@app.get("/api/v1/board/{board_id}/tags", response_model=list[models.TagResponse])
def list_tags(
    board_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    return crud.list_tags(conn, board_id=board_id)


# --- User routes (global) ---


@app.get("/api/v1/users", response_model=list[models.UserResponse])
def list_users(conn: sqlite3.Connection = Depends(get_db)):
    return crud.list_users(conn)


@app.post("/api/v1/users/new", response_model=models.UserResponse, status_code=201)
def create_user(
    user: models.UserCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    import sqlite3 as _sqlite3

    report_to_id = None
    if user.report_to:
        report_to_id = crud.resolve_username(conn, user.report_to)
        if report_to_id is None:
            raise HTTPException(status_code=404, detail=f"report_to user '{user.report_to}' not found")

    try:
        return crud.create_user(conn, user.external_id, user.display_name, username=user.username, report_to=report_to_id)
    except _sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"User with external_id '{user.external_id}' already exists"
        )


@app.post("/api/v1/users/{user_id}/edit", response_model=models.UserResponse)
def edit_user(
    user_id: int,
    user_update: models.UserUpdate,
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


@app.post("/api/v1/users/{user_id}/delete")
def delete_user(
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    if not crud.delete_user(conn, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


# --- Attachment routes ---


def _safe_filename(name: str) -> str:
    """Sanitize filename to alphanumeric, dots, and hyphens only."""
    safe = re.sub(r"[^a-zA-Z0-9.\-]", "_", name)
    # Collapse multiple underscores
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_") or "file"


async def _handle_upload(
    conn: sqlite3.Connection,
    board_id: int,
    task_id: int,
    file: UploadFile,
    request: Request,
    comment_id: int | None = None,
) -> dict:
    """Shared upload logic for task-level and comment-level uploads."""
    original_name = file.filename or "unnamed"
    safe_name = f"{uuid4()}_{_safe_filename(original_name)}"
    content_type = file.content_type or ""

    file_path = _get_upload_dir() / safe_name
    content = await file.read()
    file_path.write_bytes(content)
    size = len(content)

    uploader_id = _resolve_actor(conn, request)

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
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return await _handle_upload(conn, board_id, task_id, file, request)


@app.post(
    "/api/v1/board/{board_id}/tasks/{task_id}/comments/{comment_id}/upload",
    response_model=models.AttachmentResponse,
    status_code=201,
)
async def upload_comment_file(
    board_id: int,
    task_id: int,
    comment_id: int,
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    comment = crud.get_comment(conn, comment_id)
    if comment is None or comment["task_id"] != task_id:
        raise HTTPException(status_code=404, detail="Comment not found")

    return await _handle_upload(conn, board_id, task_id, file, request, comment_id=comment_id)


@app.get(
    "/api/v1/board/{board_id}/tasks/{task_id}/attachments",
    response_model=list[models.AttachmentResponse],
)
def list_attachments(
    board_id: int,
    task_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    _require_board(conn, board_id)
    task = crud.get_task(conn, board_id=board_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return crud.get_attachments(conn, task_id)


@app.get("/api/v1/files/{attachment_id}")
def serve_file(
    attachment_id: int,
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
    conn: sqlite3.Connection = Depends(get_db),
):
    attachment = crud.get_attachment(conn, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete file from disk
    file_path = _get_upload_dir() / attachment["filename"]
    if file_path.exists():
        file_path.unlink()

    crud.delete_attachment(conn, attachment_id)
    return {"ok": True}


# --- Static web client ---

# Installed package has server/static/, dev repo has client_web/dist/
_pkg_static = Path(__file__).resolve().parent / "static"
_dev_static = Path(__file__).resolve().parent.parent / "client_web" / "dist"
STATIC_DIR = _pkg_static if _pkg_static.is_dir() else _dev_static

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        """Serve static files if they exist, otherwise fall back to index.html for SPA routing."""
        # Serve exact static file if it exists (e.g. /favicon.svg)
        static_file = STATIC_DIR / full_path
        if full_path and static_file.is_file() and STATIC_DIR in static_file.resolve().parents:
            return FileResponse(static_file)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        raise HTTPException(status_code=404, detail="Web client not found")
