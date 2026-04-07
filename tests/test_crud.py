"""CRUD operation tests."""

import time

import pytest

from server import crud


class TestCreateUser:
    def test_creates_user(self, db):
        user = crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        assert user["id"] == 1
        assert user["external_id"] == "alice"
        assert user["display_name"] == "Alice"

    def test_duplicate_external_id_raises(self, db):
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        with pytest.raises(Exception):
            crud.create_user(db, external_id="alice", username="alicetwo", display_name="Alice 2")


class TestGetUser:
    def test_returns_user(self, db):
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        user = crud.get_user(db, 1)
        assert user is not None
        assert user["display_name"] == "Alice"

    def test_returns_none_for_missing(self, db):
        assert crud.get_user(db, 999) is None


class TestListUsers:
    def test_lists_all_users(self, populated_db):
        users = crud.list_users(populated_db)
        assert len(users) == 2

    def test_empty_db(self, db):
        assert crud.list_users(db) == []


class TestUpdateUser:
    def test_updates_name(self, db):
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        updated = crud.update_user(db, 1, display_name="Alice Updated")
        assert updated is not None
        assert updated["display_name"] == "Alice Updated"
        assert updated["external_id"] == "alice"

    def test_updates_external_id(self, db):
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        updated = crud.update_user(db, 1, external_id="alice2")
        assert updated is not None
        assert updated["external_id"] == "alice2"


# ---------------------------------------------------------------------------
# Board CRUD
# ---------------------------------------------------------------------------


class TestCreateBoard:
    def test_creates_board(self, db):
        board = crud.create_board(db, name="My Board")
        assert board["id"] == 1
        assert board["name"] == "My Board"
        assert board["description"] == ""
        assert board["created_time"] > 0

    def test_creates_board_with_description(self, db):
        board = crud.create_board(db, name="My Board", description="A board")
        assert board["description"] == "A board"


class TestGetBoard:
    def test_returns_board(self, db):
        crud.create_board(db, name="My Board")
        board = crud.get_board(db, 1)
        assert board is not None
        assert board["name"] == "My Board"

    def test_returns_none_for_missing(self, db):
        assert crud.get_board(db, 999) is None


class TestListBoards:
    def test_lists_all_boards(self, populated_db):
        boards = crud.list_boards(populated_db)
        assert len(boards) == 2

    def test_empty_db(self, db):
        assert crud.list_boards(db) == []


class TestUpdateBoard:
    def test_updates_name(self, db):
        crud.create_board(db, name="Old Name")
        updated = crud.update_board(db, 1, name="New Name")
        assert updated is not None
        assert updated["name"] == "New Name"

    def test_updates_description(self, db):
        crud.create_board(db, name="Board", description="old")
        updated = crud.update_board(db, 1, description="new desc")
        assert updated is not None
        assert updated["description"] == "new desc"

    def test_no_op_returns_board(self, db):
        crud.create_board(db, name="Board")
        result = crud.update_board(db, 1)
        assert result is not None
        assert result["name"] == "Board"


# ---------------------------------------------------------------------------
# Tag CRUD (now board-scoped)
# ---------------------------------------------------------------------------


class TestCreateTag:
    def test_creates_tag(self, db):
        board = crud.create_board(db, name="B")
        tag = crud.create_tag(db, board_id=board["id"], name="backend")
        assert tag["id"] == 1
        assert tag["name"] == "backend"

    def test_duplicate_on_same_board_raises(self, db):
        board = crud.create_board(db, name="B")
        crud.create_tag(db, board_id=board["id"], name="backend")
        with pytest.raises(Exception):
            crud.create_tag(db, board_id=board["id"], name="backend")

    def test_same_name_different_boards_ok(self, db):
        b1 = crud.create_board(db, name="B1")
        b2 = crud.create_board(db, name="B2")
        t1 = crud.create_tag(db, board_id=b1["id"], name="bug")
        t2 = crud.create_tag(db, board_id=b2["id"], name="bug")
        assert t1["id"] != t2["id"]


class TestListTags:
    def test_lists_tags_scoped_by_board(self, populated_db):
        # Board 1 has backend, frontend, urgent tags
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        board2_id = boards[1]["id"]
        tags1 = crud.list_tags(populated_db, board_id=board1_id)
        names = [t["name"] for t in tags1]
        assert "backend" in names
        assert "frontend" in names
        assert "urgent" in names

        # Board 2 should have no tags (only auto-created ones from tasks)
        tags2 = crud.list_tags(populated_db, board_id=board2_id)
        # Board 2 has no explicit tags
        assert len(tags2) == 0


# ---------------------------------------------------------------------------
# Task CRUD (now board-scoped)
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_creates_basic_task(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Test task")
        assert task["id"] == 1
        assert task["title"] == "Test task"
        assert task["status"] == "NEW"
        assert task["importance"] == 0
        assert task["estimated_effort"] == 0
        assert task["description"] == ""
        assert task["tags"] == []
        assert task["blockers"] == []

    def test_creates_task_with_all_fields(self, db):
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        crud.create_tag(db, board_id=board["id"], name="backend")
        task = crud.create_task(
            db,
            board_id=board["id"],
            title="Complex task",
            description="A complex task",
            assignee_id=1,
            importance=80,
            estimated_effort=5,
            tags=["backend"],
        )
        assert task["title"] == "Complex task"
        assert task["description"] == "A complex task"
        assert task["assignee_id"] == 1
        assert task["assignee_name"] == "Alice"
        assert task["importance"] == 80
        assert task["estimated_effort"] == 5
        assert task["tags"] == ["backend"]

    def test_creates_task_with_new_tags(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task", tags=["newtag"])
        assert task["tags"] == ["newtag"]
        tags = crud.list_tags(db, board_id=board["id"])
        assert any(t["name"] == "newtag" for t in tags)

    def test_creates_task_with_blockers(self, db):
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task 1")
        task2 = crud.create_task(db, board_id=board["id"], title="Task 2", blockers=[1])
        assert task2["blockers"] == [1]

    def test_created_time_is_set(self, db):
        board = crud.create_board(db, name="B")
        before = time.time()
        task = crud.create_task(db, board_id=board["id"], title="Task")
        after = time.time()
        assert before <= task["created_time"] <= after

    def test_requires_board_id(self, db):
        """create_task must have board_id parameter."""
        board = crud.create_board(db, name="B")
        # This should work
        task = crud.create_task(db, board_id=board["id"], title="Task")
        assert task is not None

    def test_create_with_started_status_no_comment(self, db):
        """Creating a task with status=STARTED should not generate a change comment."""
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, external_id="u", username="usr", display_name="U")
        task = crud.create_task(
            db,
            board_id=board["id"],
            title="Started task",
            assignee_id=user["id"],
            status="STARTED",
        )
        assert task["status"] == "STARTED"
        comments = crud.get_comments(db, task["id"])
        assert comments == []


class TestGetTask:
    def test_returns_task_with_tags_and_deps(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.get_task(populated_db, board_id=board1_id, task_id=1)
        assert task is not None
        assert task["title"] == "Build API"
        assert task["assignee_name"] == "Alice Smith"
        assert set(task["tags"]) == {"backend", "urgent"}
        assert task["blockers"] == []

    def test_returns_task_with_blockers(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.get_task(populated_db, board_id=board1_id, task_id=2)
        assert task is not None
        assert task["blockers"] == [1]

    def test_returns_none_for_missing(self, db):
        board = crud.create_board(db, name="B")
        assert crud.get_task(db, board_id=board["id"], task_id=999) is None

    def test_returns_none_for_wrong_board(self, populated_db):
        """Task on board 1 should not be visible when querying board 2."""
        boards = crud.list_boards(populated_db)
        board2_id = boards[1]["id"]
        # Task 1 is on board 1
        task = crud.get_task(populated_db, board_id=board2_id, task_id=1)
        assert task is None


class TestListTasks:
    def test_lists_tasks_scoped_by_board(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        board2_id = boards[1]["id"]
        tasks1 = crud.list_tasks(populated_db, board_id=board1_id)
        assert len(tasks1) == 3
        tasks2 = crud.list_tasks(populated_db, board_id=board2_id)
        assert len(tasks2) == 1
        assert tasks2[0]["title"] == "Beta task"

    def test_filter_by_status(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        tasks = crud.list_tasks(
            populated_db,
            board_id=board1_id,
            filters=[{"field": "status", "op": "eq", "value": "NEW"}],
        )
        assert len(tasks) == 3

    def test_filter_by_assignee(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        tasks = crud.list_tasks(
            populated_db,
            board_id=board1_id,
            filters=[{"field": "assignee_id", "op": "eq", "value": 1}],
        )
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Build API"

    def test_filter_by_importance_gte(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        tasks = crud.list_tasks(
            populated_db,
            board_id=board1_id,
            filters=[{"field": "importance", "op": "gte", "value": 60}],
        )
        assert len(tasks) == 2

    def test_filter_by_tag(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        tasks = crud.list_tasks(
            populated_db,
            board_id=board1_id,
            filters=[{"field": "tag", "op": "eq", "value": "urgent"}],
        )
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Build API"

    def test_no_filters(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        tasks = crud.list_tasks(populated_db, board_id=board1_id, filters=None)
        assert len(tasks) == 3

    def test_empty_board(self, db):
        board = crud.create_board(db, name="Empty")
        assert crud.list_tasks(db, board_id=board["id"]) == []


class TestUpdateTask:
    def test_updates_title(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.update_task(populated_db, board_id=board1_id, task_id=1, title="Updated API")
        assert task is not None
        assert task["title"] == "Updated API"

    def test_updates_importance(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.update_task(populated_db, board_id=board1_id, task_id=1, importance=50)
        assert task is not None
        assert task["importance"] == 50

    def test_generates_change_comment(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        crud.update_task(populated_db, board_id=board1_id, task_id=1, importance=50)
        comments = crud.get_comments(populated_db, 1)
        contents = [c["content"] for c in comments]
        assert any("IMPORTANCE=" in c and "50" in c for c in contents)

    def test_updates_multiple_fields(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.update_task(
            populated_db, board_id=board1_id, task_id=1, title="New title", description="New desc"
        )
        assert task is not None
        assert task["title"] == "New title"
        assert task["description"] == "New desc"


class TestSetTaskStatus:
    def test_sets_status(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.set_task_status(populated_db, board_id=board1_id, task_id=1, status="STARTED")
        assert task is not None
        assert task["status"] == "STARTED"

    def test_generates_status_comment(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        crud.set_task_status(populated_db, board_id=board1_id, task_id=1, status="STARTED")
        comments = crud.get_comments(populated_db, 1)
        assert any("STATUS=+STARTED" in c["content"] for c in comments)


class TestStatusTransitionRules:
    def test_done_requires_started(self, populated_db):
        boards = crud.list_boards(populated_db)
        bid = boards[0]["id"]
        # Task 1 is NEW with assignee — can't go directly to DONE
        with pytest.raises(ValueError, match="Cannot set status to DONE"):
            crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="DONE")

    def test_waiting_requires_started(self, populated_db):
        boards = crud.list_boards(populated_db)
        bid = boards[0]["id"]
        # Task 1 is NEW with assignee — can't go directly to WAITING
        with pytest.raises(ValueError, match="Cannot set status to WAITING_FOR_COMMAND_EXECUTION"):
            crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="WAITING_FOR_COMMAND_EXECUTION")

    def test_waiting_from_started_ok(self, populated_db):
        boards = crud.list_boards(populated_db)
        bid = boards[0]["id"]
        crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="STARTED")
        task = crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="WAITING_FOR_COMMAND_EXECUTION")
        assert task["status"] == "WAITING_FOR_COMMAND_EXECUTION"

    def test_done_from_started_ok(self, populated_db):
        boards = crud.list_boards(populated_db)
        bid = boards[0]["id"]
        crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="STARTED")
        task = crud.edit_task_fields(populated_db, board_id=bid, task_id=1, status="DONE")
        assert task["status"] == "DONE"


class TestAssignTask:
    def test_assigns_user(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.assign_task(populated_db, board_id=board1_id, task_id=3, user_id=2)
        assert task is not None
        assert task["assignee_id"] == 2
        assert task["assignee_name"] == "Bob Jones"

    def test_unassigns_user(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.assign_task(populated_db, board_id=board1_id, task_id=1, user_id=None)
        assert task is not None
        assert task["assignee_id"] is None
        assert task["assignee_name"] is None

    def test_generates_assignee_comment(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        crud.assign_task(populated_db, board_id=board1_id, task_id=3, user_id=1)
        comments = crud.get_comments(populated_db, 3)
        assert any("ASSIGNEE=+" in c["content"] for c in comments)

    def test_unassign_generates_comment(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        crud.assign_task(populated_db, board_id=board1_id, task_id=1, user_id=None)
        comments = crud.get_comments(populated_db, 1)
        assert any("ASSIGNEE=-" in c["content"] for c in comments)


class TestSetTaskTags:
    def test_sets_tags(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.set_task_tags(populated_db, board_id=board1_id, task_id=1, tags=["frontend"])
        assert task is not None
        assert task["tags"] == ["frontend"]

    def test_generates_add_remove_comments(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        # Task 1 has ["backend", "urgent"], set to ["frontend"]
        crud.set_task_tags(populated_db, board_id=board1_id, task_id=1, tags=["frontend"])
        comments = crud.get_comments(populated_db, 1)
        contents = [c["content"] for c in comments]
        found_add = any("TAGS+=frontend" in c for c in contents)
        found_remove_backend = any("TAGS-=backend" in c for c in contents)
        found_remove_urgent = any("TAGS-=urgent" in c for c in contents)
        assert found_add
        assert found_remove_backend
        assert found_remove_urgent

    def test_creates_new_tags_automatically(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        crud.set_task_tags(populated_db, board_id=board1_id, task_id=1, tags=["newone"])
        tags = crud.list_tags(populated_db, board_id=board1_id)
        assert any(t["name"] == "newone" for t in tags)

    def test_empty_tags(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.set_task_tags(populated_db, board_id=board1_id, task_id=1, tags=[])
        assert task is not None
        assert task["tags"] == []

    def test_tags_per_board(self, db):
        """Same tag name on different boards should create separate tag records."""
        b1 = crud.create_board(db, name="B1")
        b2 = crud.create_board(db, name="B2")
        crud.create_task(db, board_id=b1["id"], title="T1", tags=["shared"])
        crud.create_task(db, board_id=b2["id"], title="T2", tags=["shared"])
        tags1 = crud.list_tags(db, board_id=b1["id"])
        tags2 = crud.list_tags(db, board_id=b2["id"])
        assert any(t["name"] == "shared" for t in tags1)
        assert any(t["name"] == "shared" for t in tags2)
        # They should be different tag records
        tag1_id = [t["id"] for t in tags1 if t["name"] == "shared"][0]
        tag2_id = [t["id"] for t in tags2 if t["name"] == "shared"][0]
        assert tag1_id != tag2_id


class TestSetTaskBlockers:
    def test_sets_blockers(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.set_task_blockers(populated_db, board_id=board1_id, task_id=3, task_ids=[1, 2])
        assert task is not None
        assert sorted(task["blockers"]) == [1, 2]

    def test_generates_add_remove_comments(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        # Task 2 is blockers [1], set to [3]
        crud.set_task_blockers(populated_db, board_id=board1_id, task_id=2, task_ids=[3])
        comments = crud.get_comments(populated_db, 2)
        contents = [c["content"] for c in comments]
        assert any("BLOCKERS+=3" in c for c in contents)
        assert any("BLOCKERS-=1" in c for c in contents)

    def test_clear_blockers(self, populated_db):
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        task = crud.set_task_blockers(populated_db, board_id=board1_id, task_id=2, task_ids=[])
        assert task is not None
        assert task["blockers"] == []

    def test_rejects_cross_board_references(self, populated_db):
        """Cannot set blockers to a task on a different board."""
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        # Task 4 is on board 2, tasks 1-3 are on board 1
        with pytest.raises(ValueError, match="cross-board"):
            crud.set_task_blockers(populated_db, board_id=board1_id, task_id=1, task_ids=[4])


class TestAddComment:
    def test_adds_comment(self, populated_db):
        comment = crud.add_comment(populated_db, 1, "Test comment")
        assert comment["id"] == 1
        assert comment["task_id"] == 1
        assert comment["content"] == "Test comment"
        assert comment["created_time"] > 0


class TestGetComments:
    def test_returns_comments(self, populated_db):
        crud.add_comment(populated_db, 1, "Comment 1")
        crud.add_comment(populated_db, 1, "Comment 2")
        comments = crud.get_comments(populated_db, 1)
        assert len(comments) == 2

    def test_returns_empty_for_no_comments(self, populated_db):
        comments = crud.get_comments(populated_db, 1)
        assert comments == []


class TestGetComment:
    def test_returns_comment(self, populated_db):
        crud.add_comment(populated_db, 1, "Hello")
        comment = crud.get_comment(populated_db, 1)
        assert comment is not None
        assert comment["content"] == "Hello"

    def test_returns_none_for_missing(self, db):
        assert crud.get_comment(db, 999) is None


# ---------------------------------------------------------------------------
# Change-detection: no comment when value is unchanged
# ---------------------------------------------------------------------------


class TestNoChangeNoComment:
    def test_update_task_same_value_no_comment(self, db):
        """update_task with the same value should not generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task", importance=50)
        comments_before = crud.get_comments(db, 1)
        crud.update_task(db, board_id=board["id"], task_id=1, importance=50)
        comments_after = crud.get_comments(db, 1)
        assert len(comments_after) == len(comments_before)

    def test_update_task_changed_value_generates_comment(self, db):
        """update_task with a different value should generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task", importance=50)
        crud.update_task(db, board_id=board["id"], task_id=1, importance=75)
        comments = crud.get_comments(db, 1)
        assert any("IMPORTANCE=75" in c["content"] for c in comments)

    def test_update_task_mixed_changed_unchanged(self, db):
        """Only changed fields should appear in the comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task", importance=50)
        crud.update_task(db, board_id=board["id"], task_id=1, title="New Title", importance=50)
        comments = crud.get_comments(db, 1)
        assert len(comments) == 1
        assert "TITLE=New Title" in comments[0]["content"]
        assert "IMPORTANCE" not in comments[0]["content"]

    def test_set_task_status_same_no_comment(self, db):
        """set_task_status with current status should not generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task")
        # Default status is NEW
        crud.set_task_status(db, board_id=board["id"], task_id=1, status="NEW")
        comments = crud.get_comments(db, 1)
        assert len(comments) == 0

    def test_set_task_status_different_generates_comment(self, db):
        """set_task_status with a new status should generate a comment."""
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, "tester", "Tester", username="tester")
        crud.create_task(db, board_id=board["id"], title="Task", assignee_id=user["id"])
        crud.set_task_status(db, board_id=board["id"], task_id=1, status="STARTED")
        comments = crud.get_comments(db, 1)
        assert any("STATUS=+STARTED" in c["content"] for c in comments)

    def test_assign_task_same_no_comment(self, db):
        """assign_task with the current assignee should not generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        crud.create_task(db, board_id=board["id"], title="Task", assignee_id=1)
        crud.assign_task(db, board_id=board["id"], task_id=1, user_id=1)
        comments = crud.get_comments(db, 1)
        assert len(comments) == 0

    def test_assign_task_different_generates_comment(self, db):
        """assign_task with a different user should generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        crud.create_user(db, external_id="bob", username="bob", display_name="Bob")
        crud.create_task(db, board_id=board["id"], title="Task", assignee_id=1)
        crud.assign_task(db, board_id=board["id"], task_id=1, user_id=2)
        comments = crud.get_comments(db, 1)
        assert any("ASSIGNEE=+" in c["content"] for c in comments)

    def test_set_task_tags_same_no_comment(self, db):
        """set_task_tags with identical tags should not generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task", tags=["alpha", "beta"])
        crud.set_task_tags(db, board_id=board["id"], task_id=1, tags=["alpha", "beta"])
        comments = crud.get_comments(db, 1)
        assert len(comments) == 0

    def test_set_task_blockers_same_no_comment(self, db):
        """set_task_blockers with identical blockers should not generate a comment."""
        board = crud.create_board(db, name="B")
        crud.create_task(db, board_id=board["id"], title="Task 1")
        crud.create_task(db, board_id=board["id"], title="Task 2", blockers=[1])
        crud.set_task_blockers(db, board_id=board["id"], task_id=2, task_ids=[1])
        comments = crud.get_comments(db, 2)
        assert len(comments) == 0


class TestEditTaskFields:
    def test_multi_field_single_comment(self, db):
        """edit_task_fields with multiple changes should produce exactly one comment."""
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        task = crud.create_task(
            db,
            board_id=board["id"],
            title="Original",
            assignee_id=user["id"],
            importance=10,
        )
        task_id = task["id"]

        comments_before = crud.get_comments(db, task_id)

        result = crud.edit_task_fields(
            db,
            board_id=board["id"],
            task_id=task_id,
            status="STARTED",
            title="Updated",
            importance=80,
        )

        assert result is not None
        assert result["status"] == "STARTED"
        assert result["title"] == "Updated"
        assert result["importance"] == 80

        comments_after = crud.get_comments(db, task_id)
        new_comments = comments_after[len(comments_before) :]
        assert len(new_comments) == 1

        content = new_comments[0]["content"]
        assert "STATUS" in content
        assert "TITLE" in content
        assert "IMPORTANCE" in content

    def test_no_change_no_comment(self, db):
        """edit_task_fields with no actual changes should not generate a comment."""
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task", importance=50)
        task_id = task["id"]

        crud.edit_task_fields(
            db,
            board_id=board["id"],
            task_id=task_id,
            title="Task",
            importance=50,
        )

        comments = crud.get_comments(db, task_id)
        assert len(comments) == 0

    def test_returns_none_for_missing_task(self, db):
        board = crud.create_board(db, name="B")
        result = crud.edit_task_fields(db, board_id=board["id"], task_id=999, title="X")
        assert result is None


class TestBlockersFilter:
    def test_blockers_filter_finds_task(self, populated_db):
        """BLOCKERS~=<id> should find tasks blocked by the given task."""
        from server.query_lang import parse_filter, to_sql_where

        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        # Task 2 has blocker [1]
        parsed = parse_filter("BLOCKERS~=1")
        where_sql, where_params = to_sql_where(parsed)
        tasks = crud.list_tasks(
            populated_db, board_id=board1_id, where_clause=(where_sql, where_params)
        )
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Design UI"

    def test_blockers_filter_no_match(self, populated_db):
        from server.query_lang import parse_filter, to_sql_where

        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        parsed = parse_filter("BLOCKERS~=999")
        where_sql, where_params = to_sql_where(parsed)
        tasks = crud.list_tasks(
            populated_db, board_id=board1_id, where_clause=(where_sql, where_params)
        )
        assert len(tasks) == 0


class TestParentTaskId:
    def test_create_task_with_parent(self, db):
        board = crud.create_board(db, name="B")
        parent = crud.create_task(db, board_id=board["id"], title="Parent")
        child = crud.create_task(
            db, board_id=board["id"], title="Child", parent_task_id=parent["id"]
        )
        assert child["parent_task_id"] == parent["id"]

    def test_create_task_self_parent_rejected(self, db):
        """A task cannot be its own parent (DB CHECK constraint)."""
        import sqlite3
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            crud.edit_task_fields(
                db, board_id=board["id"], task_id=task["id"], parent_task_id=task["id"]
            )

    def test_create_task_cross_board_parent_rejected(self, db):
        b1 = crud.create_board(db, name="B1")
        b2 = crud.create_board(db, name="B2")
        parent = crud.create_task(db, board_id=b1["id"], title="Parent")
        with pytest.raises(ValueError, match="different board"):
            crud.create_task(
                db, board_id=b2["id"], title="Child", parent_task_id=parent["id"]
            )

    def test_edit_parent_task_id(self, db):
        board = crud.create_board(db, name="B")
        parent = crud.create_task(db, board_id=board["id"], title="Parent")
        child = crud.create_task(db, board_id=board["id"], title="Child")
        result = crud.edit_task_fields(
            db, board_id=board["id"], task_id=child["id"], parent_task_id=parent["id"]
        )
        assert result["parent_task_id"] == parent["id"]

    def test_clear_parent_task_id(self, db):
        board = crud.create_board(db, name="B")
        parent = crud.create_task(db, board_id=board["id"], title="Parent")
        child = crud.create_task(
            db, board_id=board["id"], title="Child", parent_task_id=parent["id"]
        )
        result = crud.edit_task_fields(
            db, board_id=board["id"], task_id=child["id"], parent_task_id=0
        )
        assert result["parent_task_id"] is None

    def test_circular_parent_rejected(self, db):
        board = crud.create_board(db, name="B")
        a = crud.create_task(db, board_id=board["id"], title="A")
        b = crud.create_task(
            db, board_id=board["id"], title="B", parent_task_id=a["id"]
        )
        with pytest.raises(ValueError, match="Circular"):
            crud.edit_task_fields(
                db, board_id=board["id"], task_id=a["id"], parent_task_id=b["id"]
            )

    def test_get_subtasks(self, db):
        board = crud.create_board(db, name="B")
        parent = crud.create_task(db, board_id=board["id"], title="Parent")
        crud.create_task(
            db, board_id=board["id"], title="Child 1", parent_task_id=parent["id"]
        )
        crud.create_task(
            db, board_id=board["id"], title="Child 2", parent_task_id=parent["id"]
        )
        subtasks = crud.get_subtasks(db, board_id=board["id"], task_id=parent["id"])
        assert len(subtasks) == 2
        assert {s["title"] for s in subtasks} == {"Child 1", "Child 2"}


class TestUsernameResolution:
    def test_resolve_username(self, db):
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        assert crud.resolve_username(db, "alice") == 1
        assert crud.resolve_username(db, "nonexistent") is None

    def test_create_task_with_assignee_username(self, db):
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        task = crud.create_task(
            db, board_id=board["id"], title="Task", assignee="alice"
        )
        assert task["assignee_id"] == 1
        assert task["assignee_name"] == "Alice"

    def test_create_task_with_invalid_username_raises(self, db):
        board = crud.create_board(db, name="B")
        with pytest.raises(ValueError, match="not found"):
            crud.create_task(
                db, board_id=board["id"], title="Task", assignee="nonexistent"
            )

    def test_edit_task_with_assignee_username(self, db):
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        result = crud.edit_task_fields(
            db, board_id=board["id"], task_id=task["id"], assignee="alice"
        )
        assert result["assignee_id"] == 1

    def test_add_comment_with_commenter_username(self, db):
        board = crud.create_board(db, name="B")
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        comment = crud.add_comment(db, task["id"], "Hello", commenter="alice")
        assert comment["commenter_id"] == 1
        assert comment["commenter_name"] == "Alice"


class TestCommentLevelAttachments:
    def test_create_attachment_with_comment_id(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        comment = crud.add_comment(db, task["id"], "Comment")
        att = crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="test.txt", original_name="test.txt",
            comment_id=comment["id"],
        )
        assert att["comment_id"] == comment["id"]

    def test_get_attachments_for_comment(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        comment = crud.add_comment(db, task["id"], "Comment")
        crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="a.txt", original_name="a.txt",
            comment_id=comment["id"],
        )
        crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="b.txt", original_name="b.txt",
        )
        comment_atts = crud.get_attachments_for_comment(db, comment["id"])
        assert len(comment_atts) == 1
        assert comment_atts[0]["original_name"] == "a.txt"

    def test_get_attachments_excludes_comment_attachments(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        comment = crud.add_comment(db, task["id"], "Comment")
        crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="comment_file.txt", original_name="comment_file.txt",
            comment_id=comment["id"],
        )
        crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="task_file.txt", original_name="task_file.txt",
        )
        task_atts = crud.get_attachments(db, task["id"])
        assert len(task_atts) == 1
        assert task_atts[0]["original_name"] == "task_file.txt"

    def test_task_level_attachment_has_null_comment_id(self, db):
        board = crud.create_board(db, name="B")
        task = crud.create_task(db, board_id=board["id"], title="Task")
        att = crud.create_attachment(
            db, board_id=board["id"], task_id=task["id"],
            filename="test.txt", original_name="test.txt",
        )
        assert att["comment_id"] is None


class TestBatchEnrichment:
    def test_batch_enrichment_matches_single(self, populated_db):
        """Batch enrichment should return same results as single enrichment."""
        boards = crud.list_boards(populated_db)
        board1_id = boards[0]["id"]
        # Get all tasks via list (batch enrichment)
        batch_tasks = crud.list_tasks(populated_db, board_id=board1_id)
        # Get each task individually (single enrichment)
        for bt in batch_tasks:
            single = crud.get_task(populated_db, board_id=board1_id, task_id=bt["id"])
            assert bt["tags"] == single["tags"]
            assert bt["blockers"] == single["blockers"]
            assert bt["assignee_name"] == single["assignee_name"]
            assert bt["assignee_username"] == single["assignee_username"]


class TestSecurityWhitelist:
    def test_update_user_rejects_unknown_fields(self, db):
        """update_user should ignore fields not in the whitelist."""
        crud.create_user(db, external_id="alice", username="alice", display_name="Alice")
        # Try to inject an arbitrary field — should be silently ignored
        result = crud.update_user(db, 1, display_name="Updated", id=999)
        assert result["id"] == 1  # id should NOT have changed
        assert result["display_name"] == "Updated"

    def test_update_board_rejects_unknown_fields(self, db):
        crud.create_board(db, name="Board")
        result = crud.update_board(db, 1, name="Updated", id=999)
        assert result["id"] == 1
        assert result["name"] == "Updated"


class TestListTasksSortAndLimit:
    def test_sort_by_importance_desc(self, populated_db):
        tasks = crud.list_tasks(populated_db, board_id=1, sort_by="importance_desc")
        importances = [t["importance"] for t in tasks]
        assert importances == sorted(importances, reverse=True)

    def test_sort_by_importance_asc(self, populated_db):
        tasks = crud.list_tasks(populated_db, board_id=1, sort_by="importance_asc")
        importances = [t["importance"] for t in tasks]
        assert importances == sorted(importances)

    def test_limit_returns_at_most_n(self, populated_db):
        all_tasks = crud.list_tasks(populated_db, board_id=1)
        assert len(all_tasks) == 3  # sanity check
        limited = crud.list_tasks(populated_db, board_id=1, limit=2)
        assert len(limited) == 2

    def test_sort_and_limit_combined(self, populated_db):
        tasks = crud.list_tasks(populated_db, board_id=1, sort_by="importance_desc", limit=1)
        assert len(tasks) == 1
        assert tasks[0]["importance"] == 80  # highest importance task


class TestAccessTokenCrud:
    def test_create_stores_hash_not_raw(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        from server.auth import generate_token

        _raw, token_hash = generate_token()
        token = crud.create_access_token(db, user["id"], token_hash, label="cli")
        assert token["id"] is not None
        # DB should have the hash, not the raw token
        row = db.execute("SELECT token_hash FROM access_tokens WHERE id = ?", (token["id"],)).fetchone()
        assert row[0] == token_hash

    def test_list_excludes_hash(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        from server.auth import generate_token

        _raw, token_hash = generate_token()
        crud.create_access_token(db, user["id"], token_hash, label="cli")
        tokens = crud.list_access_tokens(db, user["id"])
        assert len(tokens) == 1
        assert "token_hash" not in tokens[0]
        assert tokens[0]["label"] == "cli"

    def test_revoke(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        from server.auth import generate_token

        _raw, token_hash = generate_token()
        token = crud.create_access_token(db, user["id"], token_hash, label="cli")
        assert crud.revoke_access_token(db, token["id"])
        tokens = crud.list_access_tokens(db, user["id"])
        assert len(tokens) == 0

    def test_revoke_nonexistent_returns_false(self, db):
        assert not crud.revoke_access_token(db, 9999)


class TestRoleCrud:
    def test_set_role(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        updated = crud.update_user(db, user["id"], role="admin")
        assert updated["role"] == "admin"

    def test_set_invalid_role_id_raises(self, db):
        import sqlite3

        user = crud.create_user(db, "ext1", "Alice", username="alice")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE users SET role_id = 9999 WHERE id = ?", (user["id"],))
            db.commit()

    def test_default_role_is_null(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        assert user.get("role") is None


class TestBoardPermissionCrud:
    def test_set_and_get(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        board = crud.create_board(db, name="B")
        crud.set_board_permission(db, user["id"], board["id"], "write")
        perm = crud.get_board_permission(db, user["id"], board["id"])
        assert perm == "write"

    def test_get_default_returns_none(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        board = crud.create_board(db, name="B")
        perm = crud.get_board_permission(db, user["id"], board["id"])
        assert perm is None

    def test_list_board_permissions(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        board = crud.create_board(db, name="B")
        crud.set_board_permission(db, user["id"], board["id"], "read")
        perms = crud.list_board_permissions(db, board["id"])
        assert len(perms) == 1
        assert perms[0]["permission"] == "read"

    def test_update_existing(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        board = crud.create_board(db, name="B")
        crud.set_board_permission(db, user["id"], board["id"], "read")
        crud.set_board_permission(db, user["id"], board["id"], "write")
        perm = crud.get_board_permission(db, user["id"], board["id"])
        assert perm == "write"


class TestUserDisabled:
    def test_disable_user(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        updated = crud.update_user(db, user["id"], disabled=1)
        assert updated["disabled"] == 1

    def test_reenable_user(self, db):
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        crud.update_user(db, user["id"], disabled=1)
        updated = crud.update_user(db, user["id"], disabled=0)
        assert updated["disabled"] == 0


class TestTaskAccessLog:
    def test_record_access(self, db):
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        task = crud.create_task(db, board_id=board["id"], title="T")
        t = time.time()
        crud.record_task_access(db, user["id"], task["id"], t)
        row = db.execute(
            "SELECT last_accessed_time FROM task_access_log WHERE user_id = ? AND task_id = ?",
            (user["id"], task["id"]),
        ).fetchone()
        assert row[0] == t

    def test_update_on_re_access(self, db):
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        task = crud.create_task(db, board_id=board["id"], title="T")
        t1 = time.time()
        crud.record_task_access(db, user["id"], task["id"], t1)
        t2 = t1 + 100
        crud.record_task_access(db, user["id"], task["id"], t2)
        row = db.execute(
            "SELECT last_accessed_time FROM task_access_log WHERE user_id = ? AND task_id = ?",
            (user["id"], task["id"]),
        ).fetchone()
        assert row[0] == t2

    def test_nullable_timestamp(self, db):
        board = crud.create_board(db, name="B")
        user = crud.create_user(db, "ext1", "Alice", username="alice")
        task = crud.create_task(db, board_id=board["id"], title="T")
        crud.record_task_access(db, user["id"], task["id"], None)
        row = db.execute(
            "SELECT last_accessed_time FROM task_access_log WHERE user_id = ? AND task_id = ?",
            (user["id"], task["id"]),
        ).fetchone()
        assert row[0] is None
