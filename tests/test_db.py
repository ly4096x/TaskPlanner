"""Schema tests for the database layer."""

import sqlite3

import pytest

from server.db import get_connection, get_db_path, init_db


class TestGetDbPath:
    def test_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("TASKPLANNER_DATA_DIR", raising=False)
        with pytest.raises(RuntimeError, match="TASKPLANNER_DATA_DIR not set"):
            get_db_path()

    def test_respects_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TASKPLANNER_DATA_DIR", str(tmp_path))
        path = get_db_path()
        assert path == tmp_path / "taskplanner.db"


class TestGetConnection:
    def test_connection_has_row_factory(self):
        with get_connection(":memory:") as conn:
            assert conn.row_factory == sqlite3.Row

    def test_wal_mode_enabled(self):
        with get_connection(":memory:") as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()
            # In-memory databases may report "memory" instead of "wal"
            assert result[0] in ("wal", "memory")

    def test_foreign_keys_enabled(self):
        with get_connection(":memory:") as conn:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1

    def test_connection_closes_after_context(self):
        with get_connection(":memory:") as conn:
            conn.execute("SELECT 1")
        # After context manager exits, connection should be closed
        with pytest.raises(Exception):
            conn.execute("SELECT 1")


class TestInitDb:
    def test_creates_all_tables(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        expected = {
            "users",
            "tags",
            "tasks",
            "task_tags",
            "task_dependencies",
            "comments",
            "boards",
            "_schema_version",
            "attachments",
        }
        assert tables == expected

    def test_idempotent(self, db):
        # Running init_db again should not raise
        init_db(db)
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "tasks" in tables
        assert "boards" in tables


class TestSchema:
    def test_users_table_columns(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        assert cols == {"id", "external_id", "username", "display_name", "report_to"}

    def test_users_external_id_unique(self, db):
        db.execute(
            "INSERT INTO users (external_id, username, display_name) VALUES ('u1', 'userone', 'User 1')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO users (external_id, username, display_name) VALUES ('u1', 'usertwo', 'User 2')"
            )

    def test_boards_table_exists(self, db):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "boards" in tables

    def test_boards_table_columns(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(boards)").fetchall()}
        assert cols == {"id", "name", "description", "created_time"}

    def test_tags_table_columns(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(tags)").fetchall()}
        assert cols == {"id", "name", "board_id"}

    def test_tags_unique_constraint_is_board_id_name(self, db):
        """Same tag name on different boards should be allowed."""
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B1', ?)", (t,))
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B2', ?)", (t,))
        # Same tag name on different boards: OK
        db.execute("INSERT INTO tags (board_id, name) VALUES (1, 'bug')")
        db.execute("INSERT INTO tags (board_id, name) VALUES (2, 'bug')")
        # Same tag name on same board: should fail
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO tags (board_id, name) VALUES (1, 'bug')")

    def test_tasks_table_has_board_id(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(tasks)").fetchall()}
        expected = {
            "id",
            "title",
            "assignee_id",
            "description",
            "importance",
            "estimated_effort",
            "created_time",
            "status",
            "board_id",
            "parent_task_id",
        }
        assert cols == expected

    def test_tasks_board_id_fk(self, db):
        """Tasks board_id must reference an existing board."""
        import time

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time) VALUES (999, 'bad', ?)",
                (time.time(),),
            )

    def test_tags_board_id_fk(self, db):
        """Tags board_id must reference an existing board."""
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO tags (board_id, name) VALUES (999, 'bad')")

    def test_tasks_status_check_constraint(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time, status) VALUES (1, ?, ?, ?)",
                ("t", t, "INVALID"),
            )

    def test_tasks_importance_check_constraint(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time, importance) VALUES (1, ?, ?, ?)",
                ("t", t, 101),
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time, importance) VALUES (1, ?, ?, ?)",
                ("t", t, -1),
            )

    def test_tasks_estimated_effort_check_constraint(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time, estimated_effort) VALUES (1, ?, ?, ?)",
                ("t", t, -1),
            )

    def test_task_tags_foreign_keys(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (999, 999)")

    def test_task_dependencies_self_reference_check(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute(
            "INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)",
            ("t", t),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO task_dependencies (task_id, blockers) VALUES (1, 1)")

    def test_comments_table_columns(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(comments)").fetchall()}
        assert cols == {"id", "task_id", "commenter_id", "content", "comment_type", "created_time"}

    def test_cascade_delete_task_removes_comments(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute("INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)", ("t", t))
        db.execute(
            "INSERT INTO comments (task_id, content, created_time) VALUES (1, 'hello', ?)",
            (t,),
        )
        db.execute("DELETE FROM tasks WHERE id = 1")
        count = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        assert count == 0

    def test_cascade_delete_task_removes_tags(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute("INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)", ("t", t))
        db.execute("INSERT INTO tags (board_id, name) VALUES (1, 'bug')")
        db.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (1, 1)")
        db.execute("DELETE FROM tasks WHERE id = 1")
        count = db.execute("SELECT COUNT(*) FROM task_tags").fetchone()[0]
        assert count == 0

    def test_cascade_delete_task_removes_dependencies(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute("INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)", ("t1", t))
        db.execute("INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)", ("t2", t))
        db.execute("INSERT INTO task_dependencies (task_id, blockers) VALUES (2, 1)")
        db.execute("DELETE FROM tasks WHERE id = 2")
        count = db.execute("SELECT COUNT(*) FROM task_dependencies").fetchone()[0]
        assert count == 0

    def test_delete_user_sets_null_on_tasks(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute(
            "INSERT INTO users (external_id, username, display_name) VALUES ('u1', 'userone', 'User 1')"
        )
        db.execute(
            "INSERT INTO tasks (board_id, title, assignee_id, created_time) VALUES (1, ?, 1, ?)",
            ("t", t),
        )
        db.execute("DELETE FROM users WHERE id = 1")
        row = db.execute("SELECT assignee_id FROM tasks WHERE id = 1").fetchone()
        assert row[0] is None

    def test_cascade_delete_board_removes_tasks(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute("INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)", ("t", t))
        db.execute("DELETE FROM boards WHERE id = 1")
        count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        assert count == 0

    def test_parent_task_id_self_reference_check(self, db):
        """parent_task_id != id CHECK constraint."""
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute(
            "INSERT INTO tasks (board_id, title, created_time) VALUES (1, ?, ?)",
            ("t", t),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE tasks SET parent_task_id = 1 WHERE id = 1")

    def test_parent_task_id_fk(self, db):
        """parent_task_id must reference an existing task."""
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO tasks (board_id, title, created_time, parent_task_id) VALUES (1, ?, ?, ?)",
                ("t", t, 999),
            )

    def test_attachments_comment_id_column(self, db):
        cols = {row[1] for row in db.execute("PRAGMA table_info(attachments)").fetchall()}
        assert "comment_id" in cols

    def test_indexes_exist(self, db):
        indexes = {
            row[1]
            for row in db.execute(
                "SELECT * FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        assert "idx_comments_task_id" in indexes
        assert "idx_attachments_task_id" in indexes
        assert "idx_attachments_comment_id" in indexes
        assert "idx_tasks_parent_task_id" in indexes

    def test_cascade_delete_board_removes_tags(self, db):
        import time

        t = time.time()
        db.execute("INSERT INTO boards (name, created_time) VALUES ('B', ?)", (t,))
        db.execute("INSERT INTO tags (board_id, name) VALUES (1, 'bug')")
        db.execute("DELETE FROM boards WHERE id = 1")
        count = db.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        assert count == 0
