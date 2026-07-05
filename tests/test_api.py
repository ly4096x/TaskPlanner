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

    def test_edit_blockers_and_blocked_status_in_one_call(self, aclient):
        # #745: a dependency discovered mid-work — one edit call must be able
        # to attach the new blocker AND transition to BLOCKED; the transition
        # is validated against the blockers being set, not the stored ones.
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={"external_id": "blk-u", "username": "blocku", "display_name": "B"},
        ).json()
        blocker = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "dep"}
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "work", "assignee_id": user["id"], "status": "STARTED"},
        ).json()
        assert task["blockers"] == []
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "BLOCKED", "blockers": [blocker["id"]]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "BLOCKED"
        assert body["blockers"] == [blocker["id"]]

    def test_edit_blocked_with_empty_blockers_still_rejected(self, aclient):
        board = _create_board(aclient)
        user = aclient.post(
            "/api/v1/users",
            json={"external_id": "blk-u2", "username": "blocku2", "display_name": "B"},
        ).json()
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "work", "assignee_id": user["id"], "status": "STARTED"},
        ).json()
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "BLOCKED", "blockers": []},
        )
        assert resp.status_code == 422

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

        # #531: lowercase fields and spaces around the operator must work too.
        for expr in ("status = STARTED", "status=STARTED", "STATUS = STARTED"):
            resp = aclient.get(
                f"/api/v1/board/{board['id']}/tasks", params={"filter": expr}
            )
            assert resp.status_code == 200, expr
            assert [t["title"] for t in resp.json()] == ["Started task"], expr

    def test_malformed_filter_returns_400_not_500(self, aclient):
        """#531: a filter that can't be parsed is a client error, not a 500."""
        board = _create_board(aclient)
        for bad in ("STATUS??NEW", "FOOBAR=1", "=NEW", "STATUS"):
            resp = aclient.get(
                f"/api/v1/board/{board['id']}/tasks", params={"filter": bad}
            )
            assert resp.status_code == 400, f"{bad!r} -> {resp.status_code}"
            assert "Invalid filter" in resp.json()["detail"]

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


class TestLastActivity:
    """last_activity_time = max(task created_time, latest comment of any type)."""

    def _mk(self, aclient, name):
        board = _create_board(aclient, name=name)
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        return board, task

    def test_fresh_task_equals_created_time(self, aclient):
        board, task = self._mk(aclient, "LA1")
        assert task["last_activity_time"] == task["created_time"]
        fetched = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}").json()
        assert fetched["last_activity_time"] == fetched["created_time"]
        listed = aclient.get(f"/api/v1/board/{board['id']}/tasks").json()
        assert [t["last_activity_time"] for t in listed if t["id"] == task["id"]] == [
            task["created_time"]
        ]

    def test_comment_bumps_last_activity(self, aclient):
        board, task = self._mk(aclient, "LA2")
        comment = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "bump"},
        ).json()
        fetched = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}").json()
        assert fetched["last_activity_time"] == comment["created_time"]
        assert fetched["last_activity_time"] >= task["created_time"]

    def test_edit_bumps_last_activity(self, aclient):
        board, task = self._mk(aclient, "LA3")
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit", json={"title": "T2"}
        )
        comments = aclient.get(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments"
        ).json()
        assert comments  # the edit recorded a METADATA_CHANGE comment
        fetched = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}").json()
        assert fetched["last_activity_time"] == max(c["created_time"] for c in comments)

    def test_sort_by_last_activity(self, aclient, db_conn):
        board = _create_board(aclient, name="LA4")
        t1 = aclient.post(f"/api/v1/board/{board['id']}/tasks/new", json={"title": "a"}).json()
        t2 = aclient.post(f"/api/v1/board/{board['id']}/tasks/new", json={"title": "b"}).json()
        aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{t1['id']}/new_comment",
            json={"content": "bump"},
        )
        # Pin timestamps so ordering is deterministic: t1 was created first but
        # its comment makes it the most recently active task.
        db_conn.execute("UPDATE tasks SET created_time = 1000 WHERE id = ?", (t1["id"],))
        db_conn.execute("UPDATE tasks SET created_time = 2000 WHERE id = ?", (t2["id"],))
        db_conn.execute("UPDATE comments SET created_time = 3000 WHERE task_id = ?", (t1["id"],))
        db_conn.commit()

        desc = aclient.get(f"/api/v1/board/{board['id']}/tasks?sort=last_activity_desc").json()
        assert [t["id"] for t in desc] == [t1["id"], t2["id"]]
        assert desc[0]["last_activity_time"] == 3000
        asc = aclient.get(f"/api/v1/board/{board['id']}/tasks?sort=last_activity_asc").json()
        assert [t["id"] for t in asc] == [t2["id"], t1["id"]]


class TestCommentPermissions:
    """new_comment must be gated by the granular tasks.post_comment action
    (not legacy boards.write), and the task creator may always comment."""

    # Mirrors the hook-created 'agent' role: granular task perms, no boards.write.
    AGENT_PERMS = ["boards.read", "tasks.read", "tasks.create", "tasks.edit", "tasks.post_comment"]

    def _user_client(self, client, db_conn, username, perms):
        role = crud.create_role(db_conn, f"role_{username}", permissions=perms)
        user = crud.create_user(db_conn, f"{username}-ext", username.title(), username=username)
        crud.update_user(db_conn, user["id"], role_id=role["id"])
        raw, token_hash = auth.generate_token()
        crud.create_access_token(db_conn, user["id"], token_hash, label="test")
        return user, AuthClient(client, {"Authorization": f"Bearer {raw}"})

    def test_post_comment_allowed_without_boards_write(self, client, aclient, db_conn):
        board = _create_board(aclient, name="CP1")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        _, agent_client = self._user_client(client, db_conn, "agentlike", self.AGENT_PERMS)
        resp = agent_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "hello"},
        )
        assert resp.status_code == 201

    def test_post_comment_denied_without_permission(self, client, aclient, db_conn):
        board = _create_board(aclient, name="CP2")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        _, reader_client = self._user_client(
            client, db_conn, "readerlike", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "nope"},
        )
        assert resp.status_code == 403

    def test_creator_can_always_comment(self, client, aclient, db_conn):
        board = _create_board(aclient, name="CP3")
        # Creator role can create tasks but has no comment permission.
        _, creator_client = self._user_client(
            client, db_conn, "creator1", ["boards.read", "tasks.read", "tasks.create"]
        )
        task = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "Mine"}
        ).json()
        resp = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "my own task"},
        )
        assert resp.status_code == 201

    def test_non_creator_without_permission_denied(self, client, aclient, db_conn):
        board = _create_board(aclient, name="CP4")
        _, creator_client = self._user_client(
            client, db_conn, "creator2", ["boards.read", "tasks.read", "tasks.create"]
        )
        task = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "Mine"}
        ).json()
        _, other_client = self._user_client(
            client, db_conn, "other2", ["boards.read", "tasks.read", "tasks.create"]
        )
        resp = other_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "not mine"},
        )
        assert resp.status_code == 403

    def test_task_response_includes_creator_id(self, client, aclient, db_conn):
        board = _create_board(aclient, name="CP5")
        creator, creator_client = self._user_client(
            client, db_conn, "creator3", ["boards.read", "tasks.read", "tasks.create"]
        )
        task = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "Mine"}
        ).json()
        assert task["creator_id"] == creator["id"]
        fetched = aclient.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}").json()
        assert fetched["creator_id"] == creator["id"]
        listed = aclient.get(f"/api/v1/board/{board['id']}/tasks").json()
        assert [t["creator_id"] for t in listed if t["id"] == task["id"]] == [creator["id"]]

    def test_legacy_task_null_creator_permissions(self, client, aclient, db_conn):
        # Pre-v19 tasks have creator_id NULL: nobody gets the creator bypass,
        # so only the granular permission (or admin) allows commenting.
        board = _create_board(aclient, name="CP6")
        legacy = crud.create_task(db_conn, board_id=board["id"], title="legacy")
        assert legacy["creator_id"] is None
        _, reader_client = self._user_client(
            client, db_conn, "reader6", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/{legacy['id']}/new_comment",
            json={"content": "nope"},
        )
        assert resp.status_code == 403
        _, commenter_client = self._user_client(
            client, db_conn, "commenter6", ["boards.read", "tasks.read", "tasks.post_comment"]
        )
        resp = commenter_client.post(
            f"/api/v1/board/{board['id']}/tasks/{legacy['id']}/new_comment",
            json={"content": "ok"},
        )
        assert resp.status_code == 201

    def test_roleless_creator_can_still_comment(self, client, aclient, db_conn):
        # Strongest form of "creator can always comment": the creator's role
        # is later revoked entirely (role_id NULL denies every board action).
        board = _create_board(aclient, name="CP7")
        creator, creator_client = self._user_client(
            client, db_conn, "creator7", ["boards.read", "tasks.read", "tasks.create"]
        )
        task = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "Mine"}
        ).json()
        # crud.update_user(role_id=None) is a no-op (None means "unset"); clear via SQL.
        db_conn.execute("UPDATE users SET role_id = NULL WHERE id = ?", (creator["id"],))
        db_conn.commit()
        resp = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "still my task"},
        )
        assert resp.status_code == 201

    def test_comment_on_nonexistent_board_404(self, aclient):
        resp = aclient.post(
            "/api/v1/board/99999/tasks/1/new_comment", json={"content": "x"}
        )
        assert resp.status_code == 404

    def test_missing_task_403_before_404_for_unprivileged(self, client, aclient, db_conn):
        # Permission check runs before existence check so users without
        # tasks.post_comment can't probe whether a task id exists.
        board = _create_board(aclient, name="CP8")
        _, reader_client = self._user_client(
            client, db_conn, "reader8", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/424242/new_comment",
            json={"content": "x"},
        )
        assert resp.status_code == 403

    def test_execution_log_comment_as_user_full_chain(self, client, aclient, db_conn):
        # The exact request the Claude Code hook sends: admin token posting an
        # EXECUTION_LOG comment attributed to the agent via as_user.
        board = _create_board(aclient, name="CP9")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        agent_user, _ = self._user_client(client, db_conn, "agentlog9", self.AGENT_PERMS)
        resp = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={
                "content": "[Tool:Bash] probe\n\n```bash\ntrue\n```",
                "comment_type": "EXECUTION_LOG",
                "as_user": agent_user["username"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["comment_type"] == "EXECUTION_LOG"
        assert body["commenter_username"] == agent_user["username"]


class TestAttachmentPermissions:
    """Uploads must be gated by the granular action of what they attach to —
    comment uploads by tasks.post_comment (creator bypass included), task
    uploads by tasks.edit — not legacy boards.write, or `add-comment -f`
    partial-writes: text lands, attachment 403s (#686)."""

    # Mirrors the hook-created 'agent' role but WITHOUT boards.write.
    AGENT_PERMS = ["boards.read", "tasks.read", "tasks.create", "tasks.edit", "tasks.post_comment"]

    def _user_client(self, client, db_conn, username, perms):
        role = crud.create_role(db_conn, f"role_{username}", permissions=perms)
        user = crud.create_user(db_conn, f"{username}-ext", username.title(), username=username)
        crud.update_user(db_conn, user["id"], role_id=role["id"])
        raw, token_hash = auth.generate_token()
        crud.create_access_token(db_conn, user["id"], token_hash, label="test")
        return user, AuthClient(client, {"Authorization": f"Bearer {raw}"})

    def _comment(self, who, board_id, task_id, content="c"):
        resp = who.post(
            f"/api/v1/board/{board_id}/tasks/{task_id}/new_comment",
            json={"content": content},
        )
        assert resp.status_code == 201
        return resp.json()

    def test_comment_upload_allowed_without_boards_write(self, client, aclient, db_conn):
        # The exact #686 repro: agent-like role, text comment succeeds, the
        # attachment upload must succeed too instead of 403ing.
        board = _create_board(aclient, name="AP1")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        _, agent_client = self._user_client(client, db_conn, "apagent1", self.AGENT_PERMS)
        comment = self._comment(agent_client, board["id"], task["id"])
        resp = agent_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments/{comment['id']}/upload",
            files={"file": ("shot.png", b"\x89PNG fakebytes", "image/png")},
        )
        assert resp.status_code == 201
        assert resp.json()["original_name"] == "shot.png"

    def test_comment_upload_denied_without_post_comment(self, client, aclient, db_conn):
        board = _create_board(aclient, name="AP2")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        comment = self._comment(aclient, board["id"], task["id"])
        _, reader_client = self._user_client(
            client, db_conn, "apreader2", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments/{comment['id']}/upload",
            files={"file": ("x.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 403

    def test_creator_can_attach_to_comment_on_own_task(self, client, aclient, db_conn):
        # Creator bypass must extend to comment attachments, matching new_comment.
        board = _create_board(aclient, name="AP3")
        _, creator_client = self._user_client(
            client, db_conn, "apcreator3", ["boards.read", "tasks.read", "tasks.create"]
        )
        task = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "Mine"}
        ).json()
        comment = self._comment(creator_client, board["id"], task["id"])
        resp = creator_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments/{comment['id']}/upload",
            files={"file": ("log.txt", b"trace", "text/plain")},
        )
        assert resp.status_code == 201

    def test_comment_upload_403_before_404_for_unprivileged(self, client, aclient, db_conn):
        # Preserve the 403-before-404 ordering on the upload path too.
        board = _create_board(aclient, name="AP4")
        _, reader_client = self._user_client(
            client, db_conn, "apreader4", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/424242/comments/1/upload",
            files={"file": ("x.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 403

    def test_task_upload_allowed_with_tasks_edit(self, client, aclient, db_conn):
        board = _create_board(aclient, name="AP5")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        _, agent_client = self._user_client(client, db_conn, "apagent5", self.AGENT_PERMS)
        resp = agent_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/upload",
            files={"file": ("a.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 201

    def test_task_upload_denied_without_tasks_edit(self, client, aclient, db_conn):
        board = _create_board(aclient, name="AP6")
        task = aclient.post(
            f"/api/v1/board/{board['id']}/tasks/new", json={"title": "T"}
        ).json()
        _, reader_client = self._user_client(
            client, db_conn, "apreader6", ["boards.read", "tasks.read"]
        )
        resp = reader_client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/upload",
            files={"file": ("a.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 403
