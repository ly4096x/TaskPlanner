"""Tests for server.auth module — token generation, hashing, verification, permissions."""

import re


class TestTokenGeneration:
    def test_has_tp_prefix(self):
        from server.auth import generate_token

        raw, _hash = generate_token()
        assert raw.startswith("tp_")

    def test_length_is_25(self):
        from server.auth import generate_token

        raw, _hash = generate_token()
        assert len(raw) == 25

    def test_base64url_charset(self):
        from server.auth import generate_token

        raw, _hash = generate_token()
        suffix = raw[3:]  # strip "tp_"
        assert re.match(r"^[A-Za-z0-9_-]+$", suffix)

    def test_uniqueness(self):
        from server.auth import generate_token

        tokens = {generate_token()[0] for _ in range(100)}
        assert len(tokens) == 100


class TestTokenHashing:
    def test_deterministic(self):
        from server.auth import hash_token

        assert hash_token("tp_abc123") == hash_token("tp_abc123")

    def test_differs_from_raw(self):
        from server.auth import hash_token

        raw = "tp_abc123"
        assert hash_token(raw) != raw

    def test_is_hex_string(self):
        from server.auth import hash_token

        h = hash_token("tp_abc123")
        assert re.match(r"^[0-9a-f]{64}$", h)


class TestTokenVerification:
    def test_valid_token_returns_user(self, db):
        from server import crud
        from server.auth import generate_token, verify_token

        user = crud.create_user(db, "ext1", "Alice", username="alice")
        raw, token_hash = generate_token()
        crud.create_access_token(db, user["id"], token_hash, label="test")
        result = verify_token(db, raw)
        assert result is not None
        assert result["username"] == "alice"

    def test_invalid_token_returns_none(self, db):
        from server.auth import verify_token

        result = verify_token(db, "tp_invalidtokenvalue12345")
        assert result is None

    def test_revoked_token_returns_none(self, db):
        from server import crud
        from server.auth import generate_token, verify_token

        user = crud.create_user(db, "ext1", "Alice", username="alice")
        raw, token_hash = generate_token()
        token = crud.create_access_token(db, user["id"], token_hash, label="test")
        crud.revoke_access_token(db, token["id"])
        result = verify_token(db, raw)
        assert result is None

    def test_disabled_user_returns_none(self, db):
        from server import crud
        from server.auth import generate_token, verify_token

        user = crud.create_user(db, "ext1", "Alice", username="alice")
        raw, token_hash = generate_token()
        crud.create_access_token(db, user["id"], token_hash, label="test")
        crud.update_user(db, user["id"], disabled=1)
        result = verify_token(db, raw)
        assert result is None

    def test_updates_last_used_time(self, db):
        from server import crud
        from server.auth import generate_token, verify_token

        user = crud.create_user(db, "ext1", "Alice", username="alice")
        raw, token_hash = generate_token()
        token = crud.create_access_token(db, user["id"], token_hash, label="test")
        assert token["last_used_time"] is None
        verify_token(db, raw)
        tokens = crud.list_access_tokens(db, user["id"])
        assert tokens[0]["last_used_time"] is not None


class TestPermissionCheck:
    def test_admin_has_access_to_everything(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Admin", username="admin")
        crud.update_user(db, user["id"], role="admin")
        board = crud.create_board(db, name="B")
        assert check_permission(db, user["id"], "admin", board["id"], "read")
        assert check_permission(db, user["id"], "admin", board["id"], "write")

    def test_member_has_write_by_default(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Member", username="member")
        crud.update_user(db, user["id"], role="member")
        board = crud.create_board(db, name="B")
        assert check_permission(db, user["id"], "member", board["id"], "read")
        assert check_permission(db, user["id"], "member", board["id"], "write")

    def test_viewer_has_read_by_default(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Viewer", username="viewer")
        crud.update_user(db, user["id"], role="viewer")
        board = crud.create_board(db, name="B")
        assert check_permission(db, user["id"], "viewer", board["id"], "read")
        assert not check_permission(db, user["id"], "viewer", board["id"], "write")

    def test_null_role_treated_as_member(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Default", username="default")
        board = crud.create_board(db, name="B")
        # role is NULL by default
        assert check_permission(db, user["id"], None, board["id"], "read")
        assert check_permission(db, user["id"], None, board["id"], "write")

    def test_board_override_grants_write_to_viewer(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Viewer", username="viewer")
        crud.update_user(db, user["id"], role="viewer")
        board = crud.create_board(db, name="B")
        crud.set_board_permission(db, user["id"], board["id"], "write")
        assert check_permission(db, user["id"], "viewer", board["id"], "write")

    def test_board_override_restricts_member_to_none(self, db):
        from server import crud
        from server.auth import check_permission

        user = crud.create_user(db, "ext1", "Member", username="member")
        crud.update_user(db, user["id"], role="member")
        board = crud.create_board(db, name="B")
        crud.set_board_permission(db, user["id"], board["id"], "none")
        assert not check_permission(db, user["id"], "member", board["id"], "read")
        assert not check_permission(db, user["id"], "member", board["id"], "write")
