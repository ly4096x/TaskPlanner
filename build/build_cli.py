#!/usr/bin/env python3
"""Build TaskPlanner CLI binary using Nuitka.

Usage:
  nix build -o dist/cli             # NixOS (standalone, via flake.nix)
  uv run python build/build_cli.py  # Other Linux (onefile, needs patchelf, gcc, python3-dev)
  python build/build_cli.py --no-onefile  # Standalone dir instead of single file
"""

import subprocess
import sys

onefile = "--no-onefile" not in sys.argv

cmd = [
    sys.executable, "-m", "nuitka",
    "--standalone",
    "--output-dir=dist",
    "--output-filename=TaskPlanner",
    "--include-package=client_cli",
    "--include-package=server.schema",
    "--include-package=shared",
    "--include-package-data=shared",
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

if onefile:
    cmd.insert(3, "--onefile")

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd)
if result.returncode != 0:
    print("\nBuild failed.", file=sys.stderr)
    sys.exit(result.returncode)

if onefile:
    print("\nBuild complete: dist/TaskPlanner")
else:
    print("\nBuild complete: dist/cli.dist/TaskPlanner")
