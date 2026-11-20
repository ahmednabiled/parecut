from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    app_env: Literal["dev", "test", "prod"] = "dev"
    secret_key: str = DEFAULT_DEV_SECRET
    database_url: str = "sqlite+aiosqlite:///./var/parecut.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    storage_dir: Path = Path("var/storage")
    storage_backend: Literal["local", "r2"] = "local"
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_endpoint_url: str | None = None
    r2_region: str = "auto"
    public_base_url: str = "http://localhost:8000"
    pipeline_runner: Literal["mock", "runpod"] = "mock"
    runpod_api_key: str | None = None
    runpod_audio_endpoint_id: str | None = None
    runpod_separate_endpoint_id: str | None = None
    runpod_api_base_url: str = "https://api.runpod.ai/v2"
    runpod_poll_interval_seconds: float = 2.0
    runpod_job_timeout_seconds: int = 14_400
    runpod_url_ttl_seconds: int = 21_600
    runpod_request_timeout_seconds: float = 30.0
    session_cookie: str = "parecut_session"
    session_ttl_days: int = 7
    signup_bonus_minutes: Decimal = Decimal("30")
    max_upload_bytes: int = 2_147_483_648
    upload_url_ttl_seconds: int = 900
    download_url_ttl_seconds: int = 900
    mock_stage_delay_ms: int = 1500
    seed_demo: bool = True
    orphan_upload_ttl_seconds: int = 86_400
    orphan_upload_cleanup_interval_seconds: int = 3_600
    frontend_dist: Path = Path("web/dist")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PARECUT_",
        extra="ignore",
    )

    def validate_runtime(self) -> None:
        if self.app_env != "prod":
            return
        if self.secret_key == DEFAULT_DEV_SECRET or len(self.secret_key) < 32:
            raise ValueError(
                "PARECUT_SECRET_KEY must be a non-default secret of at least 32 characters in prod"
            )
        if self.storage_backend == "r2" and not all(
            (
                self.r2_bucket,
                self.r2_endpoint_url,
                self.r2_access_key_id,
                self.r2_secret_access_key,
            )
        ):
            raise ValueError(
                "R2 storage backend requires bucket, endpoint, and credentials in prod"
            )
        if self.pipeline_runner == "runpod" and not all(
            (self.runpod_api_key, self.runpod_audio_endpoint_id)
        ):
            raise ValueError(
                "Runpod pipeline runner requires API key and audio endpoint ID in prod"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
