"""Run the TaskPlanner API server.

Usage: TaskPlannerServer DATA_DIR [--host HOST] [--port PORT]
"""

import argparse
import os

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="TaskPlanner API server")
    parser.add_argument("data_dir", help="Runtime data directory (DB, uploads)")
    parser.add_argument("--host", default="::1", help="Bind host (default: [::1])")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()
    os.environ["TASKPLANNER_DATA_DIR"] = args.data_dir
    uvicorn.run("server.app:app", host=args.host, port=args.port, timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()
