from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LOCAL_DB = Path(__file__).resolve().parents[1] / "milestonepay.db"
SANDBOX_URL = "https://api-m.sandbox.paypal.com"


class Settings(BaseSettings):
    # env_ignore_empty: an empty line copied from .env.example (DATABASE_URL=) means "use the default"
    # str_strip_whitespace: a stray space pasted before or after a key is ignored
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, extra="ignore", env_ignore_empty=True, str_strip_whitespace=True
    )

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_environment: str = "SANDBOX"
    paypal_webhook_id: str = ""
    openrouter_api_key: str = ""
    ai_model: str = "deepseek/deepseek-v4.1-flash-1017"
    # most real AI calls allowed per day, across everyone; 0 turns the AI off
    ai_daily_limit: int = 150
    # the sandbox Personal account that pays the demo project's invoices
    demo_client_email: str = "buyer@example.com"
    database_url: str = f"sqlite:///{LOCAL_DB}"
    # demo controls (clock and run-jobs routes); turn off for anything but a demo
    demo_mode: bool = True
    # how often the daily jobs run in the background; 0 turns the background run off
    jobs_interval_minutes: int = 60
    # when set, the freelancer side asks for this password (the client page stays open)
    app_password: str = ""

    @property
    def paypal_base_url(self) -> str:
        if self.paypal_environment.upper() != "SANDBOX":
            raise RuntimeError("MilestonePay runs against the PayPal sandbox only")
        return SANDBOX_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
