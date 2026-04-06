---
name: integration-test
description: Run the auth/ACL integration test against live server at :8000. Verifies token auth, role-based access, board permissions, and disabled user handling.
user-invocable: false
---

Run `bash tests/skills/integration-test/integration_test.sh` and verify all checks pass.

Requires:
- Server running at http://localhost:8000 with fresh DB
- `TaskPlanner` CLI in PATH
- `curl` available
