import hashlib
import io
import logging
import re
import sqlite3
from types import SimpleNamespace

import pytest

import app.provisioning as provisioning
from app.config import Settings
from app.services import build_services


class TerminalBuffer(io.StringIO):
    def isatty(self):
        return True


def test_provisioning_creates_user_and_shows_new_token_once(tmp_path, caplog):
    store = build_services(
        Settings(ai_mode="local", database_path=tmp_path / "provision.db")
    ).store
    output = TerminalBuffer()

    with caplog.at_level(logging.DEBUG):
        user_id, token_id = provisioning.issue_user_token(
            store, "Provisioned user", "developer laptop", output
        )

    output_text = output.getvalue()
    tokens = re.findall(r"eak_[A-Za-z0-9_-]{43}", output_text)
    assert len(tokens) == 1
    plaintext_token = tokens[0]
    assert output_text.count(plaintext_token) == 1
    assert "shown once" in output_text
    assert "token_hash" not in output_text
    assert store.get_active_user_for_token_hash(
        hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()
    ).user_id == user_id

    with sqlite3.connect(store.database_path) as connection:
        row = connection.execute(
            "SELECT user_id, token_hash, label FROM api_tokens WHERE token_id = ?",
            (token_id,),
        ).fetchone()
        user_count = connection.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    assert row == (
        user_id,
        hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest(),
        "developer laptop",
    )
    assert plaintext_token not in repr(row)
    assert user_count == 1
    assert plaintext_token not in caplog.text
    assert hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest() not in caplog.text


def test_provisioning_refuses_redirected_output_before_creating_user(tmp_path):
    store = build_services(
        Settings(ai_mode="local", database_path=tmp_path / "no-redirect.db")
    ).store

    with pytest.raises(RuntimeError, match="interactive terminal"):
        provisioning.issue_user_token(store, "No user", None, io.StringIO())

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_admin_cli_provisions_and_revokes_token(tmp_path, monkeypatch, capsys):
    store = build_services(
        Settings(ai_mode="local", database_path=tmp_path / "admin-cli.db")
    ).store
    monkeypatch.setattr(
        provisioning, "build_services", lambda _settings: SimpleNamespace(store=store)
    )
    output = TerminalBuffer()

    with monkeypatch.context() as patch:
        patch.setattr(provisioning.sys, "stdout", output)
        result = provisioning.main(
            ["create-user", "--display-name", "CLI user", "--label", "local admin"]
        )

    assert result == 0
    token_line = next(
        line for line in output.getvalue().splitlines() if line.startswith("eak_")
    )
    token_id = next(
        line.split(": ", 1)[1]
        for line in output.getvalue().splitlines()
        if line.startswith("Token ID:")
    )
    assert provisioning.main(["revoke", "--token-id", token_id]) == 0
    assert capsys.readouterr().out.strip() == "Token revoked."
    assert store.get_active_user_for_token_hash(
        hashlib.sha256(token_line.encode("utf-8")).hexdigest()
    ) is None
