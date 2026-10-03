"""Runtime configuration. Values come only from the environment."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    gofile_api_token: str = ""
    gofile_account_id: str = ""
    admin_telegram_id: int = 0

    database_url: str = "sqlite+aiosqlite:///./fazo_junatma.db"
    webapp_url: str = "http://localhost:8000"

    payment_card_number: str = ""
    payment_card_name: str = ""

    gofile_max_storage_gb: float = 100
    gofile_max_file_size_gb: float = 10
    gofile_storage_warning_percent: int = 80
    gofile_storage_block_percent: int = 95

    @model_validator(mode="after")
    def check_storage_thresholds(self) -> "Settings":
        if self.gofile_max_storage_gb <= 0 or self.gofile_max_file_size_gb <= 0:
            raise ValueError("GoFile size limits must be positive")
        warning = self.gofile_storage_warning_percent
        block = self.gofile_storage_block_percent
        if not 1 <= warning <= 100 or not 1 <= block <= 100:
            raise ValueError("Storage percents must be between 1 and 100")
        if warning >= block:
            raise ValueError(
                "GOFILE_STORAGE_WARNING_PERCENT must be lower than GOFILE_STORAGE_BLOCK_PERCENT"
            )
        if not (self.database_url or "").strip():
            self.database_url = "sqlite+aiosqlite:///./fazo_junatma.db"
        if not (self.webapp_url or "").strip():
            self.webapp_url = "http://localhost:8000"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def missing_runtime_settings(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    required = {
        "BOT_TOKEN": settings.bot_token,
        "GOFILE_API_TOKEN": settings.gofile_api_token,
        "GOFILE_ACCOUNT_ID": settings.gofile_account_id,
        "ADMIN_TELEGRAM_ID": settings.admin_telegram_id,
        "DATABASE_URL": settings.database_url,
        "WEBAPP_URL": settings.webapp_url,
        "PAYMENT_CARD_NUMBER": settings.payment_card_number,
        "PAYMENT_CARD_NAME": settings.payment_card_name,
        "GOFILE_MAX_STORAGE_GB": settings.gofile_max_storage_gb,
        "GOFILE_MAX_FILE_SIZE_GB": settings.gofile_max_file_size_gb,
    }
    missing: list[str] = []
    for name, value in required.items():
        if value is None or value == "" or value == 0:
            missing.append(name)
    return missing
