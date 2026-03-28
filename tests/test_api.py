"""Tests for TaskPlanner API endpoints."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

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


def _create_board(client, name="Test Board", description=""):
    resp = client.post(
        "/api/v1/boards/new",
        json={"name": name, "description": description},
    )
    assert resp.status_code == 201
    return resp.json()


# ---- User tests (global, unchanged routes) ----


class TestUsers:
    def test_list_users_empty(self, client):
        resp = client.get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_user(self, client):
        resp = client.post(
            "/api/v1/users/new",
            json={"external_id": "alice", "username": "alice", "display_name": "Alice"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["external_id"] == "alice"
        assert data["display_name"] == "Alice"
        assert "id" in data

    def test_list_users_after_create(self, client):
        client.post(
            "/api/v1/users/new",
            json={"external_id": "bob", "username": "bob", "display_name": "Bob"},
        )
        resp = client.get("/api/v1/users")
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) == 1
        assert users[0]["display_name"] == "Bob"

    def test_edit_user(self, client):
        create_resp = client.post(
            "/api/v1/users/new",
            json={"external_id": "carol", "username": "carol", "display_name": "Carol"},
        )
        user_id = create_resp.json()["id"]
        resp = client.post(
            f"/api/v1/users/{user_id}/edit",
            json={"display_name": "Caroline"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Caroline"
        assert resp.json()["external_id"] == "carol"

    def test_edit_user_not_found(self, client):
        resp = client.post("/api/v1/users/999/edit", json={"display_name": "Nobody"})
        assert resp.status_code == 404


# ---- Board tests ----


class TestBoards:
    def test_list_boards_empty(self, client):
        resp = client.get("/api/v1/boards")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_board(self, client):
        board = _create_board(client, name="My Board", description="Desc")
        assert board["name"] == "My Board"
        assert board["description"] == "Desc"
        assert "id" in board
        assert "created_time" in board

    def test_list_boards_after_create(self, client):
        _create_board(client, name="B1")
        _create_board(client, name="B2")
        resp = client.get("/api/v1/boards")
        assert resp.status_code == 200
        boards = resp.json()
        assert len(boards) == 2

    def test_get_board(self, client):
        board = _create_board(client, name="Get me")
        resp = client.get(f"/api/v1/board/{board['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get me"

    def test_get_board_not_found(self, client):
        resp = client.get("/api/v1/board/999")
        assert resp.status_code == 404

    def test_edit_board(self, client):
        board = _create_board(client, name="Old Name")
        resp = client.post(
            f"/api/v1/board/{board['id']}/edit",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_edit_board_not_found(self, client):
        resp = client.post("/api/v1/board/999/edit", json={"name": "Nope"})
        assert resp.status_code == 404


# ---- Task tests (now under /board/{board_id}/tasks) ----


class TestTasks:
    def test_list_tasks_empty(self, client):
        board = _create_board(client)
        resp = client.get(f"/api/v1/board/{board['id']}/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_task_minimal(self, client):
        board = _create_board(client)
        resp = client.post(
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

    def test_create_task_full(self, client):
        board = _create_board(client)
        # Create a user to assign
        user_resp = client.post(
            "/api/v1/users/new",
            json={"external_id": "dev1", "username": "developer", "display_name": "Developer"},
        )
        user_id = user_resp.json()["id"]

        # Create a blocker task
        blocker = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Blocker task"},
        ).json()

        resp = client.post(
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

    def test_get_task(self, client):
        board = _create_board(client)
        create_resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Get me"},
        )
        task_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/board/{board['id']}/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Get me"

    def test_get_task_not_found(self, client):
        board = _create_board(client)
        resp = client.get(f"/api/v1/board/{board['id']}/tasks/999")
        assert resp.status_code == 404

    def test_get_task_wrong_board(self, client):
        """Task on board 1 not visible via board 2."""
        board1 = _create_board(client, name="B1")
        board2 = _create_board(client, name="B2")
        task = client.post(
            f"/api/v1/board/{board1['id']}/tasks/new",
            json={"title": "Board 1 task"},
        ).json()
        resp = client.get(f"/api/v1/board/{board2['id']}/tasks/{task['id']}")
        assert resp.status_code == 404

    def test_edit_task_title(self, client):
        board = _create_board(client)
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Old title"},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"title": "New title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New title"

    def test_edit_task_status(self, client):
        board = _create_board(client)
        user = client.post(
            "/api/v1/users/new",
            json={
                "external_id": "status-user",
                "username": "statususer",
                "display_name": "Status User",
            },
        ).json()
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Status task", "assignee_id": user["id"]},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "STARTED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "STARTED"

    def test_edit_task_tags(self, client):
        board = _create_board(client)
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Tag task"},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"tags": ["alpha", "beta"]},
        )
        assert resp.status_code == 200
        assert set(resp.json()["tags"]) == {"alpha", "beta"}

    def test_edit_task_blockers(self, client):
        board = _create_board(client)
        t1 = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "T1"},
        ).json()
        t2 = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "T2"},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{t2['id']}/edit",
            json={"blockers": [t1["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["blockers"] == [t1["id"]]

    def test_edit_task_assignee(self, client):
        board = _create_board(client)
        user = client.post(
            "/api/v1/users/new",
            json={"external_id": "user1", "username": "userone", "display_name": "User One"},
        ).json()
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Assign me"},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"assignee_id": user["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] == user["id"]
        assert resp.json()["assignee_name"] == "User One"

    def test_edit_task_not_found(self, client):
        board = _create_board(client)
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/999/edit",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404

    def test_edit_task_multiple_fields(self, client):
        board = _create_board(client)
        user = client.post(
            "/api/v1/users/new",
            json={
                "external_id": "multi-user",
                "username": "multiuser",
                "display_name": "Multi User",
            },
        ).json()
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Multi edit", "assignee_id": user["id"]},
        ).json()
        resp = client.post(
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

    def test_list_tasks_with_filter(self, client):
        board = _create_board(client)
        user = client.post(
            "/api/v1/users/new",
            json={
                "external_id": "filter-user",
                "username": "filteruser",
                "display_name": "Filter User",
            },
        ).json()
        client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "New task"},
        )
        task2 = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Started task", "assignee_id": user["id"]},
        ).json()
        client.post(
            f"/api/v1/board/{board['id']}/tasks/{task2['id']}/edit",
            json={"status": "STARTED"},
        )
        resp = client.get(
            f"/api/v1/board/{board['id']}/tasks",
            params={"filter": "STATUS=STARTED"},
        )
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Started task"

    def test_board_isolation(self, client):
        """Tasks on board 1 should not appear in board 2 listing."""
        board1 = _create_board(client, name="B1")
        board2 = _create_board(client, name="B2")
        client.post(
            f"/api/v1/board/{board1['id']}/tasks/new",
            json={"title": "Board 1 only"},
        )
        client.post(
            f"/api/v1/board/{board2['id']}/tasks/new",
            json={"title": "Board 2 only"},
        )
        resp1 = client.get(f"/api/v1/board/{board1['id']}/tasks")
        resp2 = client.get(f"/api/v1/board/{board2['id']}/tasks")
        assert len(resp1.json()) == 1
        assert resp1.json()[0]["title"] == "Board 1 only"
        assert len(resp2.json()) == 1
        assert resp2.json()[0]["title"] == "Board 2 only"

    def test_tasks_on_nonexistent_board_404(self, client):
        resp = client.get("/api/v1/board/999/tasks")
        assert resp.status_code == 404

    def test_multi_field_edit_single_comment(self, client):
        """A multi-field edit should produce exactly one change comment."""
        board = _create_board(client)
        user = client.post(
            "/api/v1/users/new",
            json={
                "external_id": "combo-user",
                "username": "combouser",
                "display_name": "Combo User",
            },
        ).json()
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Original", "assignee_id": user["id"], "importance": 10},
        ).json()

        # Count comments before edit
        comments_before = client.get(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments"
        ).json()

        # Edit status + title + importance in one request
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/edit",
            json={"status": "STARTED", "title": "Updated", "importance": 80},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "STARTED"
        assert data["title"] == "Updated"
        assert data["importance"] == 80

        # Count comments after edit
        comments_after = client.get(
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


# ---- Comment tests (now under /board/{board_id}/tasks/{id}/comments) ----


class TestComments:
    def test_add_comment(self, client):
        board = _create_board(client)
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Commented task"},
        ).json()
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Hello world"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Hello world"
        assert data["task_id"] == task["id"]

    def test_get_task_comments(self, client):
        board = _create_board(client)
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Multi comment"},
        ).json()
        client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "First"},
        )
        client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Second"},
        )
        resp = client.get(f"/api/v1/board/{board['id']}/tasks/{task['id']}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) == 2
        assert comments[0]["content"] == "First"
        assert comments[1]["content"] == "Second"

    def test_get_comment_by_id(self, client):
        board = _create_board(client)
        task = client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Comment lookup"},
        ).json()
        comment = client.post(
            f"/api/v1/board/{board['id']}/tasks/{task['id']}/new_comment",
            json={"content": "Find me"},
        ).json()
        resp = client.get(f"/api/v1/board/{board['id']}/comments/{comment['id']}")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Find me"

    def test_get_comment_not_found(self, client):
        board = _create_board(client)
        resp = client.get(f"/api/v1/board/{board['id']}/comments/999")
        assert resp.status_code == 404

    def test_add_comment_task_not_found(self, client):
        board = _create_board(client)
        resp = client.post(
            f"/api/v1/board/{board['id']}/tasks/999/new_comment",
            json={"content": "Orphan"},
        )
        assert resp.status_code == 404

    def test_get_comments_task_not_found(self, client):
        board = _create_board(client)
        resp = client.get(f"/api/v1/board/{board['id']}/tasks/999/comments")
        assert resp.status_code == 404


# ---- Tag tests (now under /board/{board_id}/tags) ----


class TestTags:
    def test_list_tags_empty(self, client):
        board = _create_board(client)
        resp = client.get(f"/api/v1/board/{board['id']}/tags")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_tags_after_task_with_tags(self, client):
        board = _create_board(client)
        client.post(
            f"/api/v1/board/{board['id']}/tasks/new",
            json={"title": "Tagged", "tags": ["frontend", "bug"]},
        )
        resp = client.get(f"/api/v1/board/{board['id']}/tags")
        assert resp.status_code == 200
        tags = resp.json()
        tag_names = {t["name"] for t in tags}
        assert tag_names == {"frontend", "bug"}

    def test_tags_on_nonexistent_board_404(self, client):
        resp = client.get("/api/v1/board/999/tags")
        assert resp.status_code == 404
