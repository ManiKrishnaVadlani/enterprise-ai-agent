import importlib

import pytest

import app.config
from app.config import Settings


def test_app_name_uses_environment_value(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Agent")
    importlib.reload(app.config)
    assert app.config.APP_NAME == "Test Agent"


def test_app_name_has_safe_default(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    importlib.reload(app.config)
    assert app.config.APP_NAME == "Enterprise AI Knowledge & Workflow Agent"


def test_app_name_is_read_after_dotenv_loading(monkeypatch):
    import dotenv

    with monkeypatch.context() as patch:
        patch.delenv("APP_NAME", raising=False)
        patch.setattr(
            dotenv,
            "load_dotenv",
            lambda: patch.setenv("APP_NAME", "Loaded from dotenv"),
        )
        importlib.reload(app.config)
        assert app.config.APP_NAME == "Loaded from dotenv"
    importlib.reload(app.config)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"log_level": "TRACE"},
        {"allowed_origins": ("*",)},
        {"allowed_origins": ("https://example.com/path",)},
        {"max_concurrent_uploads": 0},
        {"upload_wait_timeout_seconds": float("inf")},
        {"rate_limit_requests": 0},
        {"rate_limit_window_seconds": 0},
        {"min_relevance_score": float("nan")},
    ],
)
def test_security_and_resource_settings_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
