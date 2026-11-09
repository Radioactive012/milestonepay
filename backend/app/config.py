from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
LOCAL_DB = Path(__file__).resolve().parents[1] / "milestonepay.db"
SANDBOX_URL = "https://api-m.sandbox.paypal.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_environment: str = "SANDBOX"
    paypal_webhook_id: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    database_url: str = f"sqlite:///{LOCAL_DB}"
    # demo controls (clock and run-jobs routes); turn off for anything but a demo
    demo_mode: bool = True
    # how often the daily jobs run in the background; 0 turns the background run off
    jobs_interval_minutes: int = 60

    @property
    def paypal_base_url(self) -> str:
        if self.paypal_environment.upper() != "SANDBOX":
            raise RuntimeError("MilestonePay runs against the PayPal sandbox only")
        return SANDBOX_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
