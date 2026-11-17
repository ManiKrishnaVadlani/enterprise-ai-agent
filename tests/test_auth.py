import hashlib
import logging
import sqlite3

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import get_authenticated_user
from app.config import Settings
from app.models import UserRecord
from app.services import build_services


pytestmark = pytest.mark.http


def _authenticated_client(tmp_path):
    services = build_services(
        Settings(ai_mode="local", database_path=tmp_path / "auth.db")
    )
    user = services.store.create_user("Test user", user_id="test-user")
    plaintext_token = "eak_test_" + ("secret" * 8)
    token_hash = hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()
    token = services.store.store_api_token_hash(user.user_id, token_hash)

    application = FastAPI()
    application.state.settings = Settings(
        ai_mode="local", database_path=tmp_path / "auth.db"
    )
    application.state.services = services

    @application.get("/protected")
    def protected(current_user: UserRecord = Depends(get_authenticated_user)):
        return {"user_id": current_user.user_id}

    return TestClient(application), services.store, user, plaintext_token, token


def test_valid_bearer_token_resolves_active_user(tmp_path):
    client, _store, user, plaintext_token, _token = _authenticated_client(tmp_path)

    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {plaintext_token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": user.user_id}


def test_missing_and_invalid_credentials_return_generic_401(tmp_path):
    client, _store, _user, _plaintext_token, _token = _authenticated_client(tmp_path)

    missing = client.get("/protected")
    invalid = client.get(
        "/protected", headers={"Authorization": "Bearer not-a-valid-token"}
    )
    wrong_scheme = client.get(
        "/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )

    for response in (missing, invalid, wrong_scheme):
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing API token."}
        assert response.headers["www-authenticate"] == "Bearer"


def test_revoked_token_returns_401(tmp_path):
    client, store, _user, plaintext_token, token = _authenticated_client(tmp_path)
    assert store.revoke_api_token(token.token_id) is True

    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {plaintext_token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API token."}


def test_inactive_user_token_returns_401(tmp_path):
    client, store, user, plaintext_token, _token = _authenticated_client(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?", (user.user_id,)
        )

    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {plaintext_token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API token."}


def test_authentication_does_not_log_plaintext_or_token_hash(tmp_path, caplog):
    client, _store, _user, plaintext_token, _token = _authenticated_client(tmp_path)
    token_hash = hashlib.sha256(plaintext_token.encode("utf-8")).hexdigest()

    with caplog.at_level(logging.DEBUG):
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {plaintext_token}"}
        )

    assert response.status_code == 200
    assert plaintext_token not in caplog.text
    assert token_hash not in caplog.text
    assert "Authorization" not in caplog.text
