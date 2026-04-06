#!/usr/bin/env bash
# End-to-end integration test for auth/ACL against a live server.
#
# Usage: bash tests/skills/integration-test/integration_test.sh [server_url] [data_dir]
#
# Requires: curl, TaskPlannerServer, TaskPlanner in PATH
# Will bootstrap admin user and create test data.

set -euo pipefail

SERVER="${1:-http://localhost:8000}"
DATA_DIR="${2:-/tmp/taskplanner-integration-test-$$}"
PASS=0
FAIL=0
H="Content-Type: application/json"

assert_status() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ✓ $desc"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $desc (expected $expected, got $actual)"
    FAIL=$((FAIL + 1))
  fi
}

get_status() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "=== TaskPlanner Auth/ACL Integration Test ==="
echo "Server: $SERVER"
echo "Data dir: $DATA_DIR"
echo ""

# --- Bootstrap admin ---
echo "--- Bootstrap admin ---"
mkdir -p "$DATA_DIR"
BOOTSTRAP_OUTPUT=$(uv run TaskPlannerServer bootstrap-admin "$DATA_DIR" --username testadmin 2>&1)
ADMIN_TOKEN=$(echo "$BOOTSTRAP_OUTPUT" | grep "Access token:" | awk '{print $3}')
echo "Admin token: ${ADMIN_TOKEN:0:10}..."

if [ -z "$ADMIN_TOKEN" ]; then
  echo "FATAL: Failed to bootstrap admin"
  exit 1
fi

AUTH_ADMIN="Authorization: Bearer $ADMIN_TOKEN"

# --- No token: all routes return 401 ---
echo ""
echo "--- No token → 401 ---"
assert_status "GET /boards no token" "401" "$(get_status "$SERVER/api/v1/boards")"
assert_status "GET /users no token" "401" "$(get_status "$SERVER/api/v1/users")"
assert_status "GET /auth/me no token" "401" "$(get_status "$SERVER/api/v1/auth/me")"

# --- Admin: verify self ---
echo ""
echo "--- Admin auth ---"
assert_status "GET /auth/me" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/auth/me")"
assert_status "GET /boards" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/boards")"
assert_status "GET /users" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/users")"

# --- Create test board ---
echo ""
echo "--- Create test board ---"
BOARD_RESP=$(curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/boards/new" -d '{"name":"IntegrationTestBoard"}')
BOARD_ID=$(echo "$BOARD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Board ID: $BOARD_ID"
assert_status "GET /board/$BOARD_ID" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/board/$BOARD_ID")"

# --- Create member user + token ---
echo ""
echo "--- Create member user ---"
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users" \
  -d '{"external_id":"member-ext","username":"testmember","display_name":"Test Member"}' > /dev/null
MEMBER_ID=$(curl -s -H "$AUTH_ADMIN" "$SERVER/api/v1/users" | python3 -c "import sys,json; print([u['id'] for u in json.load(sys.stdin) if u['username']=='testmember'][0])")
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$MEMBER_ID" -d '{"role":"member"}' > /dev/null
MEMBER_TOKEN_RESP=$(curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$MEMBER_ID/tokens" -d '{"label":"test"}')
MEMBER_TOKEN=$(echo "$MEMBER_TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
AUTH_MEMBER="Authorization: Bearer $MEMBER_TOKEN"
echo "Member token: ${MEMBER_TOKEN:0:10}..."

# --- Create viewer user + token ---
echo ""
echo "--- Create viewer user ---"
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users" \
  -d '{"external_id":"viewer-ext","username":"testviewer","display_name":"Test Viewer"}' > /dev/null
VIEWER_ID=$(curl -s -H "$AUTH_ADMIN" "$SERVER/api/v1/users" | python3 -c "import sys,json; print([u['id'] for u in json.load(sys.stdin) if u['username']=='testviewer'][0])")
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$VIEWER_ID" -d '{"role":"viewer"}' > /dev/null
VIEWER_TOKEN_RESP=$(curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$VIEWER_ID/tokens" -d '{"label":"test"}')
VIEWER_TOKEN=$(echo "$VIEWER_TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
AUTH_VIEWER="Authorization: Bearer $VIEWER_TOKEN"
echo "Viewer token: ${VIEWER_TOKEN:0:10}..."

# --- Admin permissions ---
echo ""
echo "--- Admin role ---"
assert_status "Admin: GET boards" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/boards")"
assert_status "Admin: POST boards/new" "201" "$(get_status -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/boards/new" -d '{"name":"AdminBoard"}')"
assert_status "Admin: POST users (create)" "201" "$(get_status -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users" -d '{"external_id":"x","username":"xuser","display_name":"X"}')"
assert_status "Admin: GET tasks" "200" "$(get_status -H "$AUTH_ADMIN" "$SERVER/api/v1/board/$BOARD_ID/tasks")"
assert_status "Admin: POST tasks/new" "201" "$(get_status -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/board/$BOARD_ID/tasks/new" -d '{"title":"admin task"}')"

# --- Member permissions ---
echo ""
echo "--- Member role ---"
assert_status "Member: GET boards" "200" "$(get_status -H "$AUTH_MEMBER" "$SERVER/api/v1/boards")"
assert_status "Member: POST boards/new" "201" "$(get_status -H "$AUTH_MEMBER" -H "$H" -X POST "$SERVER/api/v1/boards/new" -d '{"name":"MemberBoard"}')"
assert_status "Member: POST users → 403" "403" "$(get_status -H "$AUTH_MEMBER" -H "$H" -X POST "$SERVER/api/v1/users" -d '{"external_id":"y","username":"yuser","display_name":"Y"}')"
assert_status "Member: GET tasks" "200" "$(get_status -H "$AUTH_MEMBER" "$SERVER/api/v1/board/$BOARD_ID/tasks")"
assert_status "Member: POST tasks/new" "201" "$(get_status -H "$AUTH_MEMBER" -H "$H" -X POST "$SERVER/api/v1/board/$BOARD_ID/tasks/new" -d '{"title":"member task"}')"

# --- Viewer permissions ---
echo ""
echo "--- Viewer role ---"
assert_status "Viewer: GET boards" "200" "$(get_status -H "$AUTH_VIEWER" "$SERVER/api/v1/boards")"
assert_status "Viewer: POST boards/new → 403" "403" "$(get_status -H "$AUTH_VIEWER" -H "$H" -X POST "$SERVER/api/v1/boards/new" -d '{"name":"ViewerBoard"}')"
assert_status "Viewer: POST users → 403" "403" "$(get_status -H "$AUTH_VIEWER" -H "$H" -X POST "$SERVER/api/v1/users" -d '{"external_id":"z","username":"zuser","display_name":"Z"}')"
assert_status "Viewer: GET tasks" "200" "$(get_status -H "$AUTH_VIEWER" "$SERVER/api/v1/board/$BOARD_ID/tasks")"
assert_status "Viewer: POST tasks/new → 403" "403" "$(get_status -H "$AUTH_VIEWER" -H "$H" -X POST "$SERVER/api/v1/board/$BOARD_ID/tasks/new" -d '{"title":"viewer task"}')"

# --- Disabled user ---
echo ""
echo "--- Disabled user ---"
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$VIEWER_ID" -d '{"disabled":1}' > /dev/null
assert_status "Disabled: GET boards → 401" "401" "$(get_status -H "$AUTH_VIEWER" "$SERVER/api/v1/boards")"
# Re-enable
curl -s -H "$AUTH_ADMIN" -H "$H" -X POST "$SERVER/api/v1/users/$VIEWER_ID" -d '{"disabled":0}' > /dev/null
assert_status "Re-enabled: GET boards" "200" "$(get_status -H "$AUTH_VIEWER" "$SERVER/api/v1/boards")"

# --- CLI commands ---
echo ""
echo "--- CLI commands ---"
TASKPLANNER_USER_ACCESS_TOKEN="$ADMIN_TOKEN" uv run TaskPlanner -s "$SERVER" whoami > /dev/null 2>&1
assert_status "CLI whoami" "0" "$?"
TASKPLANNER_USER_ACCESS_TOKEN="$ADMIN_TOKEN" uv run TaskPlanner -s "$SERVER" -b "$BOARD_ID" list > /dev/null 2>&1
assert_status "CLI list" "0" "$?"

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
