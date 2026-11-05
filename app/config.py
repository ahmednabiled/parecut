from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["dev", "test", "prod"] = "dev"
    secret_key: str = "dev-only-insecure-secret-change-me"
    database_url: str = "sqlite+aiosqlite:///./var/parecut.db"
    storage_dir: Path = Path("var/storage")
    session_cookie: str = "parecut_session"
    session_ttl_days: int = 7
    signup_bonus_minutes: Decimal = Decimal("30")
    max_upload_bytes: int = 2_147_483_648
    upload_url_ttl_seconds: int = 900
    download_url_ttl_seconds: int = 900
    mock_stage_delay_ms: int = 1500
    seed_demo: bool = True
    frontend_dist: Path = Path("web/dist")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PARECUT_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
