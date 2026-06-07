"""Tests for TaskPlanner API endpoints."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from server import auth, crud
from server.app import app, get_db
from server.db import init_db


@pytest.fixture
def db_conn():
    """Create an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db_conn):
    """Create a test client with dependency override for the database."""

    def override_get_db():
        yield db_conn

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(db_conn):
    """Create an admin user and return auth headers."""
    user = crud.create_user(db_conn, "admin-ext", "Admin User", username="admin")
    # Get the admin role_id from seeded roles
    admin_role = db_conn.execute("SELECT id FROM roles WHERE name = 'admin'").fetchone()
    crud.update_user(db_conn, user["id"], role="admin", role_id=admin_role[0] if admin_role else None)
    raw, token_hash = auth.generate_token()
    crud.create_access_token(db_conn, user["id"], token_hash, label="test")
    return raw


@pytest.fixture
def admin_headers(admin_token):
    """Return Authorization headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


class AuthClient:
    """Wrapper around TestClient that injects auth headers."""

    def __init__(self, client: TestClient, headers: dict):
        self._client = client
        self._headers = headers

    def get(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.post(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.delete(url, **kwargs)


@pytest.fixture
def aclient(client, admin_headers):
    """Authenticated test client (admin)."""
    return AuthClient(client, admin_headers)


@pytest.fixture
def member_token(db_conn):
    """Create a non-admin user with full board+task permissions and return token."""
    role = crud.create_role(
        db_conn, "member_test", permissions=[
            "boards.read", "boards.write",
            "tasks.read", "tasks.create", "tasks.edit", "tasks.post_comment",
        ],
    )
    user = crud.create_user(db_conn, "member-ext", "Member User", username="member")
    crud.update_user(db_conn, user["id"], role_id=role["id"])
    raw, token_hash = auth.generate_token()
    crud.create_access_token(db_conn, user["id"], token_hash, label="test")
    return raw


@pytest.fixture
def member_client(client, member_token):
    """Authenticated test client (non-admin member)."""
    return AuthClient(client, {"Authorization": f"Bearer {member_token}"})


def _create_board(aclient, name="Test Board", description=""):
    resp = aclient.post(
        "/api/v1/boards/new",
        json={"name": name, "description": description},
    )
    assert resp.status_code == 201
    return resp.json()


# ---- User tests (global, unchanged routes) ----


class TestUsers:
    def test_list_users_has_admin(self, aclient):
        resp = aclient.get("/api/v1/users")
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) >= 1
        assert any(u["username"] == "admin" for u in users)

    def test_create_user(self, aclient):
        resp = aclient.post(
            "/api/v1/users",
            json={"external_id": "alice", "username": "alice", "display_name": "Alice"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["external_id"] == "alice"
        assert data["display_name"] == "Alice"
        assert "id" in data

    def test_list_users_after_create(self, aclient):
        initial_count = len(aclient.get("/api/v1/users").json())
        aclient.post(
            "/api/v1/users",
            json={"external_id": "bob", "username": "bob", "display_name": "Bob"},
        )
        resp = aclient.get("/api/v1/users")
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) == initial_count + 1
        assert any(u["display_name"] == "Bob" for u in users)

    def test_edit_user(self, aclient):
        create_resp = aclient.post(
            "/api/v1/users",
            json={"external_id": "carol", "username": "carol", "display_name": "Carol"},
        )
        user_id = create_resp.json()["id"]
        resp = aclient.post(
            f"/api/v1/users/{user_id}",
            json={"display_name": "Caroline"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Caroline"
        assert resp.json()["external_id"] == "carol"

    def test_edit_user_not_found(self, aclient):
        resp = aclient.post("/api/v1/users/999", json={"display_name": "Nobody"})
        assert resp.status_code == 404


# ---- Board tests ----


class TestBoards:
    def test_list_boards_empty(self, aclient):
        resp = aclient.get("/api/v1/boards")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_board(self, aclient):
        board = _create_board(aclient, name="My Board", description="Desc")
        assert board["name"] == "My Board"
        assert board["description"] == "Desc"
        assert "id" in board
        assert "created_time" in board

    def test_list_boards_after_create(self, aclient):
        _create_board(aclient, name="B1")
        _create_board(aclient, name="B2")
        resp = aclient.get("/api/v1/boards")
        assert resp.status_code == 200
        boards = resp.json()
        assert len(boards) == 2

    def test_get_board(self, aclient):
        board = _create_board(aclient, name="Get me")
        resp = aclient.get(f"/api/v1/board/{board['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get me"

    def test_get_board_not_found(self, aclient):
        resp = aclient.get("/api/v1/board/999")
        assert resp.status_code == 404

    def test_edit_board(self, aclient):
        board = _create_board(aclient, name="Old Name")
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/edit",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_edit_board_not_found(self, aclient):
        resp = aclient.post("/api/v1/board/999/edit", json={"name": "Nope"})
        assert resp.status_code == 404


# ---- Task tests (now under /board/{board_id}/tasks) ----


class TestTasks:
    def test_list_tasks_empty(self, aclient):
        board = _create_board(aclient)
        resp = aclient.get(f"/api/v1/board/{board['id']}/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_task_minimal(self, aclient):
        board = _create_board(aclient)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "My first task"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My first task"
        assert data["status"] == "NEW"
        assert data["tags"] == []
        assert data["blockers"] == []
        assert data["assignee_id"] is None
        assert data["assignee_name"] is None

    def test_create_task_full(self, aclient):
        board = _create_board(aclient)
        # Create a user to assign
        user_resp = aclient.post(
            "/api/v1/users",
            json={"external_id": "dev1", "username": "developer", "display_name": "Developer"},
        )
        user_id = user_resp.json()["id"]

        # Create a blocker task
        blocker = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Blocker task"},
        ).json()

        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={
                "title": "Full task",
                "description": "A detailed task",
                "assignee_id": user_id,
                "importance": 5,
                "estimated_effort": 3,
                "tags": ["backend", "urgent"],
                "blockers": [blocker["id"]],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Full task"
        assert data["description"] == "A detailed task"
        assert data["assignee_id"] == user_id
        assert data["assignee_name"] == "Developer"
        assert data["importance"] == 5
        assert data["estimated_effort"] == 3
        assert set(data["tags"]) == {"backend", "urgent"}
        assert data["blockers"] == [blocker["id"]]

    def test_get_task(self, aclient):
        board = _create_board(aclient)
        create_resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Get me"},
        )
        task_id = create_resp.json()["id"]
        resp = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get me"

    def test_get_task_not_found(self, aclient):
        board = _create_board(aclient)
        resp = aclient.get(f"/api/v1/board/{board['id']}/tasks/999")
        assert resp.status_code == 404

    def test_get_task_wrong_board(self, aclient):
        """Task on board 1 not visible via board 2."""
        board1 = _create_board(aclient, name="B1")
        board2 = _create_board(aclient, name="B2")
        task = aclient.post(
            f"/api/v1/board/{board1['id']}/tasks/new",
            json={"title": "Board 1 task"},
        ).json()
        resp = aclient.get(f"/api/v1/board/{board2['id']}/tasks/{task['id']}")
        assert resp.status_code == 404

    def test_edit_task_title(self, aclient):
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Old title"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"title": "New title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New title"

    def test_edit_task_status(self, aclient):
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={
                "external_id": "status-user",
                "username": "statususer",
                "display_name": "Status User",
            },
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Status task", "assignee_id": user["id"]},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "STARTED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "STARTED"

    def test_edit_task_tags(self, aclient):
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Tag task"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"tags": ["alpha", "beta"]},
        )
        assert resp.status_code == 200
        assert set(resp.json()["tags"]) == {"alpha", "beta"}

    def test_edit_task_blockers(self, aclient):
        board = _create_board(aclient)
        t1 = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "T1"},
        ).json()
        t2 = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "T2"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{t2['id']}/edit",
            json={"blockers": [t1["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["blockers"] == [t1["id"]]

    def test_edit_task_assignee(self, aclient):
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={"external_id": "user1", "username": "userone", "display_name": "User One"},
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Assign me"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"assignee_id": user["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] == user["id"]
        assert resp.json()["assignee_name"] == "User One"

    def test_edit_task_not_found(self, aclient):
        board = _create_board(aclient)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/999/edit",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404

    def test_edit_task_multiple_fields(self, aclient):
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={
                "external_id": "multi-user",
                "username": "multiuser",
                "display_name": "Multi User",
            },
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Multi edit", "assignee_id": user["id"]},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={
                "title": "Updated",
                "description": "New desc",
                "importance": 10,
                "status": "STARTED",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated"
        assert data["description"] == "New desc"
        assert data["importance"] == 10
        assert data["status"] == "STARTED"

    def test_list_tasks_with_filter(self, aclient):
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={
                "external_id": "filter-user",
                "username": "filteruser",
                "display_name": "Filter User",
            },
        ).json()
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "New task"},
        )
        task2 = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Started task", "assignee_id": user["id"]},
        ).json()
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task2['id']}/edit",
            json={"status": "STARTED"},
        )
        resp = aclient.get(
            f"/api/v1/board/{board['id']}/tasks",
            params={"filter": "STATUS=STARTED"},
        )
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Started task"

    def test_board_isolation(self, aclient):
        """Tasks on board 1 should not appear in board 2 listing."""
        board1 = _create_board(aclient, name="B1")
        board2 = _create_board(aclient, name="B2")
        aclient.post(
            f"/api/v1/board/{board1['id']}/tasks/new",
            json={"title": "Board 1 only"},
        )
        aclient.post(
            f"/api/v1/board/{board2['id']}/tasks/new",
            json={"title": "Board 2 only"},
        )
        resp1 = aclient.get(f"/api/v1/board/{board1['id']}/tasks")
        resp2 = aclient.get(f"/api/v1/board/{board2['id']}/tasks")
        assert len(resp1.json()) == 1
        assert resp1.json()[0]["title"] == "Board 1 only"
        assert len(resp2.json()) == 1
        assert resp2.json()[0]["title"] == "Board 2 only"

    def test_tasks_on_nonexistent_board_404(self, aclient):
        resp = aclient.get("/api/v1/board/999/tasks")
        assert resp.status_code == 404

    def test_multi_field_edit_single_comment(self, aclient):
        """A multi-field edit should produce exactly one change comment."""
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={
                "external_id": "combo-user",
                "username": "combouser",
                "display_name": "Combo User",
            },
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Original", "assignee_id": user["id"], "importance": 10},
        ).json()

        # Count comments before edit
        comments_before = aclient.get(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments"
        ).json()

        # Edit status + title + importance in one request
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "STARTED", "title": "Updated", "importance": 80},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "STARTED"
        assert data["title"] == "Updated"
        assert data["importance"] == 80

        # Count comments after edit
        comments_after = aclient.get(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments"
        ).json()

        # Exactly 1 new comment
        new_comments = comments_after[len(comments_before) :]
        assert len(new_comments) == 1

        # The single comment contains all three changes
        content = new_comments[0]["content"]
        assert "STATUS" in content
        assert "TITLE" in content
        assert "IMPORTANCE" in content


# ---- Status-comment enforcement tests ----


class TestStatusCommentRequired:
    """Non-admin users must provide status_reason when transitioning to
    DONE / WAITING_FOR_COMMAND_EXECUTION / NOT_REPRODUCIBLE / CANCELLED.
    Admins are exempt for DONE/WAITING/CANCELLED; NOT_REPRODUCIBLE's prefix
    rule still applies to everyone."""

    def _setup_started_task(self, aclient):
        import uuid
        suffix = uuid.uuid4().hex[:8]
        board = _create_board(aclient, name=f"B-{suffix}")
        user = aclient.post(
            "/api/v1/users",
            json={
                "external_id": f"se-{suffix}",
                "username": f"se{suffix}",
                "display_name": "SE",
            },
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "T", "assignee_id": user["id"]},
        ).json()
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "STARTED"},
        )
        return board, task

    @pytest.mark.parametrize("status", ["DONE", "WAITING_FOR_COMMAND_EXECUTION", "CANCELLED"])
    def test_non_admin_rejected_without_reason(self, aclient, member_client, status):
        board, task = self._setup_started_task(aclient)
        resp = member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": status},
        )
        assert resp.status_code == 422
        assert "status_reason" in resp.json()["detail"]

    @pytest.mark.parametrize("status", ["DONE", "WAITING_FOR_COMMAND_EXECUTION", "CANCELLED"])
    def test_non_admin_succeeds_with_reason(self, aclient, member_client, status):
        board, task = self._setup_started_task(aclient)
        resp = member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": status, "status_reason": f"because of {status}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == status
        comments = member_client.get(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments"
        ).json()
        assert any(c["content"] == f"because of {status}" for c in comments)

    @pytest.mark.parametrize("status", ["DONE", "WAITING_FOR_COMMAND_EXECUTION", "CANCELLED"])
    def test_admin_succeeds_without_reason(self, aclient, status):
        board, task = self._setup_started_task(aclient)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": status},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == status

    def test_not_reproducible_prefix_check_runs_before_transition_validator(self, aclient):
        """The NOT_REPRODUCIBLE prefix rule applies to admins too. Even though the
        transition graph in schema.yaml currently has no inbound edge to
        NOT_REPRODUCIBLE, the reason-prefix check fires before the transition
        validator, so the 422 it returns is the prefix message rather than
        the transition error."""
        board, task = self._setup_started_task(aclient)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "NOT_REPRODUCIBLE", "status_reason": "just because"},
        )
        assert resp.status_code == 422
        assert "Not reproducible because:" in resp.json()["detail"]

    def test_idempotent_status_no_reason_required(self, aclient, member_client):
        """Setting status to its current value is not a transition; no reason needed."""
        board, task = self._setup_started_task(aclient)
        # member moves to DONE with reason
        member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "DONE", "status_reason": "shipped"},
        )
        # Editing title alone while status is DONE — no reason needed
        resp = member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"title": "Renamed"},
        )
        assert resp.status_code == 200

    def test_non_comment_required_transition_does_not_need_reason(self, aclient, member_client):
        """Transitioning STARTED → NEW (not in comment-required set) needs no reason."""
        board, task = self._setup_started_task(aclient)
        resp = member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "NEW"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "NEW"


# ---- Comment tests (now under /board/{board_id}/tasks/{id}/comments) ----


class TestComments:
    def test_add_comment(self, aclient):
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Commented task"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Hello world"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Hello world"
        assert data["task_id"] == task["id"]

    def test_get_task_comments(self, aclient):
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Multi comment"},
        ).json()
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "First"},
        )
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Second"},
        )
        resp = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) == 2
        assert comments[0]["content"] == "First"
        assert comments[1]["content"] == "Second"

    def test_get_comment_by_id(self, aclient):
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Comment lookup"},
        ).json()
        comment = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Find me"},
        ).json()
        resp = aclient.get(f"/api/v1/board/{board['id']}/comments/{comment['id']}")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Find me"

    def test_get_comment_not_found(self, aclient):
        board = _create_board(aclient)
        resp = aclient.get(f"/api/v1/board/{board['id']}/comments/999")
        assert resp.status_code == 404

    def test_add_comment_task_not_found(self, aclient):
        board = _create_board(aclient)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/999/new_comment",
            json={"content": "Orphan"},
        )
        assert resp.status_code == 404

    def test_add_comment_as_user_admin(self, aclient, db_conn):
        """Admin may post a comment on behalf of another user."""
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "As-user task"},
        ).json()
        # Create a target user the admin will impersonate.
        target = crud.create_user(db_conn, "tgt-ext", "Target", username="target")
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Posted on behalf", "as_user": "target"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["commenter_id"] == target["id"]
        assert data["commenter_username"] == "target"

    def test_add_comment_as_user_non_admin_forbidden(self, member_client, aclient, db_conn):
        """Non-admin caller must not be able to set as_user."""
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "As-user denied"},
        ).json()
        crud.create_user(db_conn, "victim-ext", "Victim", username="victim")
        resp = member_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Sneaky", "as_user": "victim"},
        )
        assert resp.status_code == 403

    def test_add_comment_as_user_unknown(self, aclient):
        """Admin posting with a non-existent as_user gets 400."""
        board = _create_board(aclient)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "As-user 400"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "x", "as_user": "nobody"},
        )
        assert resp.status_code == 400

    def test_get_comments_task_not_found(self, aclient):
        board = _create_board(aclient)
        resp = aclient.get(f"/api/v1/board/{board['id']}/tasks/999/comments")
        assert resp.status_code == 404


# ---- Tag tests (now under /board/{board_id}/tags) ----


class TestTags:
    def test_list_tags_empty(self, aclient):
        board = _create_board(aclient)
        resp = aclient.get(f"/api/v1/board/{board['id']}/tags")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_tags_after_task_with_tags(self, aclient):
        board = _create_board(aclient)
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Tagged", "tags": ["frontend", "bug"]},
        )
        resp = aclient.get(f"/api/v1/board/{board['id']}/tags")
        assert resp.status_code == 200
        tags = resp.json()
        tag_names = {t["name"] for t in tags}
        assert tag_names == {"frontend", "bug"}

    def test_tags_on_nonexistent_board_404(self, aclient):
        resp = aclient.get("/api/v1/board/999/tags")
        assert resp.status_code == 404
