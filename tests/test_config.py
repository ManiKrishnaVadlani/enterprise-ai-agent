from app.config import APP_NAME


def test_app_name_uses_environment_value(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test Agent")

    # Reload to evaluate the environment when the module is imported.
    import importlib
    import app.config

    importlib.reload(app.config)
    assert app.config.APP_NAME == "Test Agent"


def test_app_name_has_safe_default(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)

    import importlib
    import app.config

    importlib.reload(app.config)
    assert app.config.APP_NAME == "Enterprise AI Knowledge & Workflow Agent"


def test_app_name_is_read_after_dotenv_loading(monkeypatch):
    import importlib
    import app.config
    import dotenv

    with monkeypatch.context() as dotenv_monkeypatch:
        dotenv_monkeypatch.delenv("APP_NAME", raising=False)
        dotenv_monkeypatch.setattr(
            dotenv,
            "load_dotenv",
            lambda: dotenv_monkeypatch.setenv("APP_NAME", "Loaded from dotenv"),
        )

        importlib.reload(app.config)
        assert app.config.APP_NAME == "Loaded from dotenv"

    importlib.reload(app.config)
