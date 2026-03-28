"""Shared fixtures for tests."""

import pytest

from server import crud
from server.db import get_connection, init_db


@pytest.fixture
def db():
    """Provide an in-memory database with schema initialized."""
    with get_connection(":memory:") as conn:
        init_db(conn)
        yield conn


@pytest.fixture
def populated_db(db):
    """Provide an in-memory database pre-populated with sample data."""
    conn = db

    # Create boards
    board1 = crud.create_board(conn, name="Project Alpha", description="First project")
    board2 = crud.create_board(conn, name="Project Beta", description="Second project")

    # Create users (global)
    crud.create_user(conn, external_id="alice", username="alice", display_name="Alice Smith")
    crud.create_user(conn, external_id="bob", username="bob", display_name="Bob Jones")

    # Create tags on board 1
    crud.create_tag(conn, board_id=board1["id"], name="backend")
    crud.create_tag(conn, board_id=board1["id"], name="frontend")
    crud.create_tag(conn, board_id=board1["id"], name="urgent")

    # Create tasks on board 1
    crud.create_task(
        conn,
        board_id=board1["id"],
        title="Build API",
        description="Build the REST API",
        assignee_id=1,
        importance=80,
        estimated_effort=5,
        tags=["backend", "urgent"],
    )
    crud.create_task(
        conn,
        board_id=board1["id"],
        title="Design UI",
        description="Design the user interface",
        assignee_id=2,
        importance=60,
        estimated_effort=3,
        tags=["frontend"],
        blockers=[1],
    )
    crud.create_task(
        conn,
        board_id=board1["id"],
        title="Write docs",
        description="Write documentation",
        importance=30,
        estimated_effort=2,
    )

    # Create a task on board 2 for isolation testing
    crud.create_task(
        conn,
        board_id=board2["id"],
        title="Beta task",
        description="A task on board 2",
        importance=50,
        estimated_effort=1,
    )

    yield conn
