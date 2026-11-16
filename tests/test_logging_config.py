import logging

import pytest

from app.logging_config import configure_logging


def test_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_logging_uses_environment_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_logging_rejects_unknown_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
        configure_logging()
