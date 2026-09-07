#!/usr/bin/env python3
"""Seed a live TaskPlanner server with the demo dataset.

Reads client_web/src/lib/demo-data.json — the same fixture the GitHub Pages
demo bakes in — and pushes it through the real HTTP API, so a screenshot of a
seeded server and the Pages demo show the same believable board.

    uv run python scripts/seed_demo.py http://127.0.0.1:8000 <admin token>

Idempotence is deliberately NOT attempted: run it against a fresh data dir
(bootstrap-admin first; the admin user must be the first user in the fixture).
Comments are posted as their fixture author via admin-minted tokens, so the
board reads as a conversation between people and agents rather than one
admin talking to itself.
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE = sys.argv[1].rstrip("/")
ADMIN_TOKEN = sys.argv[2]
DATA = json.loads(
    (Path(__file__).parent.parent / "client_web/src/lib/demo-data.json").read_text()
)


def call(path, payload=None, token=None, method=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token or ADMIN_TOKEN}",
        },
        method=method or ("POST" if payload is not None else "GET"),
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    me = call("/api/v1/auth/me")
    tokens = {me["username"]: ADMIN_TOKEN}
    user_ids = {me["username"]: me["id"]}
    # The bootstrap admin's display name is its username; give it the fixture's.
    admin_fixture = next((u for u in DATA["users"] if u["username"] == me["username"]), None)
    if admin_fixture:
        call(f"/api/v1/users/{me['id']}", {"display_name": admin_fixture["display_name"]})

    # Only `admin` is built in; every other user needs a role that grants the
    # board actions, or its comments 403. One role, all board actions, as the
    # default for every board (a NULL board_id row is the fallback).
    contributor = call(
        "/api/v1/roles",
        {
            "name": "contributor",
            "description": "Can read and edit every board (demo default)",
            "permissions": [
                "boards.read", "boards.write", "tasks.read",
                "tasks.create", "tasks.edit", "tasks.post_comment",
            ],
        },
    )

    for u in DATA["users"]:
        if u["username"] in tokens:
            continue
        made = call("/api/v1/users", {k: u[k] for k in ("external_id", "username", "display_name")})
        user_ids[u["username"]] = made["id"]
        role = u.get("role") if u.get("role") == "admin" else contributor["name"]
        call(f"/api/v1/users/{made['id']}", {"role": role})
        tokens[u["username"]] = call(f"/api/v1/users/{made['id']}/tokens", {"label": "seed"})["token"]
        print(f"user {u['username']} ({role}) -> id {made['id']}")

    board_ids = {}
    for b in DATA["boards"]:
        made = call("/api/v1/boards/new", {"name": b["name"], "description": b.get("description", "")})
        board_ids[b["name"]] = made["id"]
        print(f"board {b['name']} -> id {made['id']}")

    task_ids = {}  # title -> (board_id, task_id)
    for t in DATA["tasks"]:
        bid = board_ids[t["board"]]
        payload = {
            "title": t["title"],
            "description": t.get("description", ""),
            "importance": t.get("importance", 0),
            "estimated_effort": t.get("estimated_effort", 0),
            "assignee": t.get("assignee"),
            "tags": t.get("tags", []),
        }
        if t.get("blockers_by_title"):
            payload["blockers"] = [task_ids[x][1] for x in t["blockers_by_title"]]
        if t.get("parent_by_title"):
            payload["parent_task_id"] = task_ids[t["parent_by_title"]][1]
        made = call(f"/api/v1/board/{bid}/tasks/new", payload)
        task_ids[t["title"]] = (bid, made["id"])

        # Tasks are born NEW; walk the legal transitions to the fixture status.
        want = t["status"]
        path = {
            "NEW": [],
            "STARTED": ["STARTED"],
            "DONE": ["STARTED", "DONE"],
            "BLOCKED": ["STARTED", "BLOCKED"],
            "WAITING_FOR_COMMAND_EXECUTION": ["STARTED", "WAITING_FOR_COMMAND_EXECUTION"],
            "CANCELLED": ["CANCELLED"],
            "NOT_REPRODUCIBLE": ["NOT_REPRODUCIBLE"],
        }[want]
        for step in path:
            body = {"status": step}
            if step == "NOT_REPRODUCIBLE":
                body["status_reason"] = (
                    "Not reproducible because: 600 requests over three hours produced zero failures"
                )
            call(f"/api/v1/board/{bid}/tasks/{made['id']}/edit", body)
        print(f"task #{made['id']} [{want}] {t['title'][:60]}")

        for c in t.get("comments", []):
            call(
                f"/api/v1/board/{bid}/tasks/{made['id']}/new_comment",
                {"content": c["text"]},
                token=tokens[c["by"]],
            )

    print("\nseeded:", len(user_ids), "users,", len(board_ids), "boards,", len(task_ids), "tasks")


if __name__ == "__main__":
    main()
