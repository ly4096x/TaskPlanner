#!/usr/bin/env python3
"""Build script for Nuitka CLI binary.

Usage: python3 build_cli.py
Output: dist/TaskPlanner (single ELF binary)
"""

import subprocess
import sys

cmd = [
    sys.executable, "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--output-dir=dist",
    "--output-filename=TaskPlanner",
    "--include-package=client_cli",
    "--include-package=server.schema",
    "--include-package=shared",
    "--include-package-data=shared",
    "--enable-plugin=anti-bloat",
    "--nofollow-import-to=server.app",
    "--nofollow-import-to=server.crud",
    "--nofollow-import-to=server.db",
    "--nofollow-import-to=server.events",
    "--nofollow-import-to=server.models",
    "--nofollow-import-to=server.query_lang",
    "--nofollow-import-to=server.__main__",
    "--nofollow-import-to=fastapi",
    "--nofollow-import-to=uvicorn",
    "--nofollow-import-to=pydantic",
    "--nofollow-import-to=starlette",
    "--nofollow-import-to=sqlite3",
    "--python-flag=-O",
    "client_cli/cli.py",
]

print(f"Running: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
print("\nBuild complete: dist/TaskPlanner")
