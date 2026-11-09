from pathlib import Path

from app.config import Settings


def test_env_example_copied_as_is_gives_working_defaults(monkeypatch):
    """A judge copies .env.example to .env without filling it in: the app must still start."""
    example = Path(__file__).resolve().parents[2] / ".env.example"
    for key in ("DATABASE_URL", "DEMO_CLIENT_EMAIL", "APP_PASSWORD", "AI_DAILY_LIMIT", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=example)
    assert settings.database_url.startswith("sqlite:///")
    assert settings.demo_client_email == "buyer@example.com"
    assert settings.app_password == ""
    assert settings.ai_daily_limit == 150
    assert settings.paypal_base_url.startswith("https://api-m.sandbox.paypal.com")


def test_empty_environment_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("JOBS_INTERVAL_MINUTES", "")
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite:///")
    assert settings.jobs_interval_minutes == 60
