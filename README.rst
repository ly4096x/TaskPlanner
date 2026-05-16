===========
TaskPlanner
===========

Task management system with a FastAPI backend, a Click-based CLI client, and a
Svelte web client.

Components
==========

- ``server/`` – FastAPI HTTP API (entry point: ``TaskPlannerServer``).
- ``client_cli/`` – Python CLI (entry point: ``TaskPlanner``).
- ``client_web/`` – Svelte 5 + Vite single-page app.
- ``shared/`` – ``schema.yaml`` shared by the server, CLI, and web client.
- ``build/`` – Nuitka build script and Containerfile.

Requirements
============

- Python 3.13+
- ``uv`` (recommended) or ``pip``
- Node.js 22+ and ``pnpm`` (for the web client)
- C toolchain + ``patchelf`` (only required for the Nuitka binary build)
- Nix with flakes (optional alternative install path)
- Podman or Docker (optional, for the container build)

Setup
=====

Clone the repository and install the Python package in editable mode together
with the dev tools::

    git clone <repo-url> TaskPlanner
    cd TaskPlanner
    uv sync                       # installs runtime + dev dependencies
    # or, without uv:
    python3.13 -m venv .venv && . .venv/bin/activate
    pip install -e '.[dev]'

This makes the ``TaskPlanner`` and ``TaskPlannerServer`` console scripts
available inside the project environment.

Running the server
==================

Pick a directory for the SQLite database and uploaded attachments, then start
the API::

    mkdir -p ./runtime_data
    uv run TaskPlannerServer ./runtime_data --host 127.0.0.1 --port 8000

Default host is ``[::1]`` and default port is ``8000``. Set
``TASKPLANNER_DATA_DIR`` to override the data directory when launching by other
means.

Bootstrap an admin user
-----------------------

The first user must be created out of band. This prints an access token::

    uv run TaskPlannerServer bootstrap-admin ./runtime_data --username liuy

Export the token (the value after ``Access token:``) so the CLI can authenticate
as that user::

    export TASKPLANNER_USER_ACCESS_TOKEN=<token>

Container image
---------------

A two-stage ``Containerfile`` builds the web client and the Python server::

    podman build -f build/Containerfile -t taskplanner .
    podman run --rm -p 8000:8000 -v $PWD/runtime_data:/data taskplanner

The image runs ``TaskPlannerServer /data --host 0.0.0.0 --port 8000`` by
default and serves the built web client from the same port at ``/``.

Running the CLI
===============

With the project environment active, invoke the CLI directly::

    uv run TaskPlanner --help

Point it at the server and a board::

    export TASKPLANNER_SERVER=http://localhost:8000
    export TASKPLANNER_BOARD_ID=1
    # alternative: drop TASKPLANNER_BOARD_ID=1 into a .env file at the repo root
    export TASKPLANNER_USER_ACCESS_TOKEN=<token from bootstrap-admin>

    TaskPlanner list-boards
    TaskPlanner create-board --name "My Board"
    TaskPlanner -b 1 add-task --title "First task"

The ``taskplanner`` skill (``client_cli/agent/skills/taskplanner/SKILL.md``)
contains the full command reference, filter syntax, and status rules.

Building a standalone CLI binary
--------------------------------

Nuitka produces a single executable that does not need a Python install::

    uv run python build/build_cli.py              # onefile binary -> dist/TaskPlanner
    uv run python build/build_cli.py --no-onefile # standalone dir  -> dist/cli.dist/TaskPlanner

The onefile artifact can be copied to ``~/.local/bin/TaskPlanner`` for use
outside the project environment.

Nix flake
---------

The flake builds the server + CLI as a regular Python application and provides
a dev shell with everything needed for the Nuitka build::

    nix build .#                  # build the package
    nix develop                   # enter a dev shell

Running the web client
======================

From the repository root::

    cd client_web
    pnpm install
    pnpm dev                      # dev server with HMR on http://localhost:5173

The Vite dev server proxies ``/api`` to ``http://localhost:8000``, so start the
backend first.

Production build::

    pnpm build                    # writes client_web/dist/

When the Python package is installed (``pip install .`` or via the
``Containerfile``), ``client_web/dist`` is bundled into ``server/static`` by
hatchling and served by the FastAPI app — no separate web server is needed in
production.

Tests
=====

Python tests::

    uv run pytest

Web client tests::

    cd client_web && pnpm test

Layout reference
================

::

    pyproject.toml                # Python package definition + entry points
    flake.nix                     # Nix package + dev shell
    server/                       # FastAPI app, CRUD, schema, query language
    client_cli/                   # Click CLI and Claude Code hook integration
    client_web/                   # Svelte 5 + Vite SPA
    shared/schema.yaml            # Source of truth for statuses, transitions,
                                  # comment/event types, and filter fields
    build/                        # build_cli.py (Nuitka), Containerfile
    tests/                        # Pytest suite
