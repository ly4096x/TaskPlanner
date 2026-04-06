"""Run the TaskPlanner API server.

Usage:
  TaskPlannerServer DATA_DIR [--host HOST] [--port PORT]
  TaskPlannerServer bootstrap-admin DATA_DIR --username USERNAME
"""

import argparse
import os
import sys

import uvicorn


def bootstrap_admin(data_dir: str, username: str) -> None:
    """Create or promote a user to admin and generate their initial access token."""
    os.environ["TASKPLANNER_DATA_DIR"] = data_dir

    from server import auth, crud
    from server.db import get_connection, init_db

    with get_connection() as conn:
        init_db(conn)

        user_id = crud.resolve_username(conn, username)
        if user_id is None:
            user = crud.create_user(conn, username, username, username=username)
            user_id = user["id"]
            print(f"Created user: {username} (id={user_id})")
        else:
            print(f"Found existing user: {username} (id={user_id})")

        crud.update_user(conn, user_id, role="admin")
        print("Set role to admin")

        raw, token_hash = auth.generate_token()
        crud.create_access_token(conn, user_id, token_hash, label="bootstrap")
        print(f"\nAccess token: {raw}")
        print("\nSet in environment:")
        print(f"  export TASKPLANNER_USER_ACCESS_TOKEN={raw}")


def main():
    # Check for bootstrap-admin subcommand manually to avoid argparse conflicts
    if len(sys.argv) >= 2 and sys.argv[1] == "bootstrap-admin":
        parser = argparse.ArgumentParser(description="Bootstrap admin user")
        parser.add_argument("_cmd")  # consume "bootstrap-admin"
        parser.add_argument("data_dir", help="Runtime data directory")
        parser.add_argument("--username", required=True, help="Admin username")
        args = parser.parse_args()
        bootstrap_admin(args.data_dir, args.username)
    else:
        parser = argparse.ArgumentParser(description="TaskPlanner API server")
        parser.add_argument("data_dir", help="Runtime data directory (DB, uploads)")
        parser.add_argument("--host", default="::1", help="Bind host (default: [::1])")
        parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
        args = parser.parse_args()
        os.environ["TASKPLANNER_DATA_DIR"] = args.data_dir
        uvicorn.run("server.app:app", host=args.host, port=args.port, timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()
