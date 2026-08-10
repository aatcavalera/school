from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    upload_tmp_dir: str = "/tmp/school_import"
    environment: str = "production"
    log_level: str = "INFO"
    credential_encryption_key: str | None = None
    sync_poll_seconds: float = 2.0
    sync_worker_concurrency: int = 2
    attendance_sync_start_local: str = "05:30"
    attendance_sync_end_local: str = "17:00"
    attendance_sync_weekdays: str = "0,1,2,3,4,5"
    allow_legacy_import: bool = False
    sync_success_retention_days: int = 90
    sync_error_retention_days: int = 180
    sync_job_retention_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
