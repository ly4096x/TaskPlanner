---
name: taskplanner
description: TaskPlanner CLI reference — commands, filter syntax, status rules. Use when working with TaskPlanner tasks, or when you need to look up CLI usage.
user-invocable: false
---

# TaskPlanner CLI Reference

`TaskPlanner` is installed in PATH (`~/.local/bin`). Do NOT use `uv run` to invoke it. `TASKPLANNER_USERNAME` is set automatically by the Claude Code hook — do not set it manually.

## Commands

```bash
TaskPlanner list                              # list tasks (default: exclude CANCELLED/NOT_REPRODUCIBLE, limit 100)
TaskPlanner list -f "STATUS=NEW"              # filter tasks
TaskPlanner list -L 0                         # list all (no limit)
TaskPlanner list --format json                # JSON output
TaskPlanner show-task <id>                    # show task detail
TaskPlanner add-task --title "..." [opts]     # create task
TaskPlanner edit <id> --status STARTED        # edit task fields
TaskPlanner add-comment <id> -m "text"        # add comment
TaskPlanner add-comment <id> -m "text" -f file.png  # comment with attachment
TaskPlanner list-users                        # list users
TaskPlanner show-user --username "..."        # show user info (or --agent-session-id)
TaskPlanner list-boards                       # list boards
TaskPlanner show-board <id>                   # show board details
TaskPlanner create-board --name "..."         # create board
TaskPlanner add-user --username "..." --display-name "..." --external-id "..."  # create user
TaskPlanner watch                             # watch for SSE events
TaskPlanner watch --stop                      # stop running watcher
```

### add-task options
```
TaskPlanner add-task --title TEXT [--description TEXT] [--assignee USERNAME]
    [--importance 0-100] [--effort INT] [--tags TAG1,TAG2,...]
    [--blockers ID1,ID2,...] [--parent TASK_ID] [--start-now]
```

### edit options
```
TaskPlanner edit TASK_ID [--status STATUS] [--assignee USERNAME]
    [--title TEXT] [--description TEXT] [--importance 0-100]
    [--effort INT] [--parent TASK_ID]  # use --parent 0 to clear
```

### add-comment options
```
TaskPlanner add-comment TASK_ID -m TEXT [-f FILE]... [-t TEXT|EXECUTION_LOG]
```

### list options
`-f/--filter`, `-L/--limit`, `-T/--template`, `--format [table|json]`

## Status transitions

Statuses: `NEW`, `STARTED`, `BLOCKED`, `WAITING_FOR_COMMAND_EXECUTION`, `DONE`, `NOT_REPRODUCIBLE`, `CANCELLED`.

- Non-NEW status requires an assignee first.
- DONE can only be reached from STARTED.
- BLOCKED requires active (non-DONE/CANCELLED) blockers.
- NOT_REPRODUCIBLE requires a reason starting with "Not reproducible because:".

## Handing a task back to the user

When you need more information or input from the user before you can continue a task, **do not just stop**. Instead:

1. Post a comment explaining what you need:
   ```bash
   TaskPlanner add-comment <id> -m "Need clarification on ..."
   ```
2. Reassign the task to the human user with status NEW:
   ```bash
   TaskPlanner edit <id> --status NEW --assignee <uid 0 username>
   ```

This ensures the user sees what's blocking progress and can respond.

## Filter syntax (`-f` / `--filter`)

Fields: `ID`, `TITLE`, `STATUS`, `DESCRIPTION`, `ASSIGNEE`, `IMPORTANCE`, `ESTIMATED_EFFORT`, `CREATED_TIME`, `TAGS`, `BLOCKERS`, `PARENT`.

Operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `~=` (contains/substring match).

- Numeric fields (`ID`, `IMPORTANCE`, `ESTIMATED_EFFORT`, `CREATED_TIME`): comparisons are numeric.
- `CREATED_TIME`: supports relative values with `+`/`-` seconds (e.g. `CREATED_TIME>=-3600` = last hour).
- List fields (`TAGS`, `BLOCKERS`): `=` checks membership, `!=` checks absence.
- Boolean logic: `AND`, `OR`, `NOT`, parentheses `()`. Comma `,` is implicit `AND`.
- Quoted values: use `"..."` for values containing spaces or special characters.

Examples:
```
STATUS=NEW                                  # simple equality
STATUS=NEW,IMPORTANCE>=50                   # implicit AND (comma)
STATUS=NEW AND IMPORTANCE>=50               # explicit AND
STATUS=NEW OR STATUS=STARTED                # OR
NOT STATUS=DONE                             # NOT
(STATUS=NEW OR STATUS=STARTED) AND TAGS=bug # grouping
TITLE~=login                                # substring match
CREATED_TIME>=-86400                        # created in last 24h
TAGS=backend                                # has tag "backend"
```
