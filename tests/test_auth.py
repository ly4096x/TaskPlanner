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


class TestPerBoardPermissions:
    """Tests for the per-board role ACL system."""

    def _make_role_with_perms(self, db, name, default_perms, board_perms=None):
        """Helper: create a role with default + per-board permissions."""
        from server import crud

        role = crud.create_role(db, name, permissions=default_perms)
        if board_perms:
            for board_id, actions in board_perms.items():
                for action in actions:
                    db.execute(
                        "INSERT INTO role_permissions (role_id, action, board_id) VALUES (?, ?, ?)",
                        (role["id"], action, board_id),
                    )
                db.commit()
        return role

    def _make_user_with_role(self, db, username, role_id):
        from server import crud

        user = crud.create_user(db, username, username.title(), username=username)
        crud.update_user(db, user["id"], role_id=role_id)
        return {**user, "role_id": role_id}

    def test_admin_always_allowed(self, db):
        from server import crud
        from server.auth import check_board_action, check_global_action

        admin_rid = db.execute("SELECT id FROM roles WHERE name = 'admin'").fetchone()[0]
        user = self._make_user_with_role(db, "adminuser", admin_rid)
        board = crud.create_board(db, name="B")
        assert check_board_action(db, user, board["id"], "boards.read")
        assert check_board_action(db, user, board["id"], "tasks.write")
        assert check_global_action(db, user, "users.manage")
        assert check_global_action(db, user, "boards.create")

    def test_custom_role_default_grants_action(self, db):
        from server import crud
        from server.auth import check_board_action

        role = self._make_role_with_perms(db, "editor", ["boards.read", "tasks.read", "tasks.write"])
        user = self._make_user_with_role(db, "editoruser", role["id"])
        board = crud.create_board(db, name="B")
        assert check_board_action(db, user, board["id"], "tasks.write")

    def test_custom_role_default_denies_missing_action(self, db):
        from server import crud
        from server.auth import check_board_action

        role = self._make_role_with_perms(db, "reader", ["boards.read", "tasks.read"])
        user = self._make_user_with_role(db, "readeruser", role["id"])
        board = crud.create_board(db, name="B")
        assert not check_board_action(db, user, board["id"], "tasks.write")

    def test_board_override_grants_action_not_in_default(self, db):
        from server import crud
        from server.auth import check_board_action

        board = crud.create_board(db, name="B")
        # Default: read-only. Board override: also write.
        role = self._make_role_with_perms(
            db, "reader_plus", ["boards.read", "tasks.read"],
            board_perms={board["id"]: ["boards.read", "tasks.read", "tasks.write"]},
        )
        user = self._make_user_with_role(db, "rpuser", role["id"])
        assert check_board_action(db, user, board["id"], "tasks.write")

    def test_board_override_completely_replaces_default(self, db):
        from server import crud
        from server.auth import check_board_action

        board1 = crud.create_board(db, name="B1")
        board2 = crud.create_board(db, name="B2")
        # Default: read+write. Board1 override: read-only (no write).
        role = self._make_role_with_perms(
            db, "mixed", ["boards.read", "tasks.read", "tasks.write"],
            board_perms={board1["id"]: ["boards.read", "tasks.read"]},
        )
        user = self._make_user_with_role(db, "mixeduser", role["id"])
        # Board1: override applies (read only)
        assert check_board_action(db, user, board1["id"], "tasks.read")
        assert not check_board_action(db, user, board1["id"], "tasks.write")
        # Board2: default applies (read+write)
        assert check_board_action(db, user, board2["id"], "tasks.write")

    def test_board_override_denies_action_in_default(self, db):
        from server import crud
        from server.auth import check_board_action

        board = crud.create_board(db, name="B")
        # Default has tasks.write, but board override does NOT
        role = self._make_role_with_perms(
            db, "restricted", ["boards.read", "tasks.read", "tasks.write"],
            board_perms={board["id"]: ["boards.read", "tasks.read"]},
        )
        user = self._make_user_with_role(db, "ruser", role["id"])
        assert not check_board_action(db, user, board["id"], "tasks.write")

    def test_no_override_falls_back_to_default(self, db):
        from server import crud
        from server.auth import check_board_action

        role = self._make_role_with_perms(db, "defaultrole", ["boards.read", "tasks.read"])
        user = self._make_user_with_role(db, "defuser", role["id"])
        board = crud.create_board(db, name="B")
        # No per-board override → uses default
        assert check_board_action(db, user, board["id"], "boards.read")
        assert not check_board_action(db, user, board["id"], "tasks.write")

    def test_global_action_boards_create(self, db):
        from server.auth import check_global_action

        role = self._make_role_with_perms(db, "creator", ["boards.create", "boards.read"])
        user = self._make_user_with_role(db, "creatoruser", role["id"])
        assert check_global_action(db, user, "boards.create")

    def test_global_action_users_manage(self, db):
        from server.auth import check_global_action

        role = self._make_role_with_perms(db, "manager", ["users.manage"])
        user = self._make_user_with_role(db, "mgruser", role["id"])
        assert check_global_action(db, user, "users.manage")

    def test_global_action_denied_without_permission(self, db):
        from server.auth import check_global_action

        role = self._make_role_with_perms(db, "noroles", ["boards.read"])
        user = self._make_user_with_role(db, "nouser", role["id"])
        assert not check_global_action(db, user, "users.manage")
        assert not check_global_action(db, user, "boards.create")

    def test_tasks_post_comment_per_board(self, db):
        from server import crud
        from server.auth import check_board_action

        board1 = crud.create_board(db, name="B1")
        board2 = crud.create_board(db, name="B2")
        role = self._make_role_with_perms(
            db, "commenter", ["boards.read", "tasks.read"],
            board_perms={board1["id"]: ["boards.read", "tasks.read", "tasks.post_comment"]},
        )
        user = self._make_user_with_role(db, "cuser", role["id"])
        assert check_board_action(db, user, board1["id"], "tasks.post_comment")
        assert not check_board_action(db, user, board2["id"], "tasks.post_comment")

    def test_role_without_any_permissions_denied_everything(self, db):
        from server import crud
        from server.auth import check_board_action, check_global_action

        role = self._make_role_with_perms(db, "empty", [])
        user = self._make_user_with_role(db, "emptyuser", role["id"])
        board = crud.create_board(db, name="B")
        assert not check_board_action(db, user, board["id"], "boards.read")
        assert not check_global_action(db, user, "users.manage")

    def test_null_role_id_denied(self, db):
        from server import crud
        from server.auth import check_board_action, check_global_action

        user = crud.create_user(db, "ext1", "NoRole", username="norole")
        board = crud.create_board(db, name="B")
        user_dict = {"id": user["id"], "role_id": None}
        assert not check_board_action(db, user_dict, board["id"], "boards.read")
        assert not check_global_action(db, user_dict, "users.manage")
