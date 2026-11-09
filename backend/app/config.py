from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SANDBOX_URL = "https://api-m.sandbox.paypal.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_environment: str = "SANDBOX"
    paypal_webhook_id: str = ""
    anthropic_api_key: str = ""
    database_url: str = ""

    @property
    def paypal_base_url(self) -> str:
        if self.paypal_environment.upper() != "SANDBOX":
            raise RuntimeError("MilestonePay runs against the PayPal sandbox only")
        return SANDBOX_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
