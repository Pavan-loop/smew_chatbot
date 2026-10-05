from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)
    environment: Literal["development", "production", "test"] = "development"
    openai_api_key: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_API")
    )
    chat_model: str = "gpt-4o-mini"
    extractor_model: str = "gpt-4o-mini"
    openai_api_base: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = Field(default=20, ge=1, le=60)
    database_path: Path = Path("./data/smew.sqlite3")
    railway_volume_mount_path: Path | None = None
    session_secret: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    allowed_origins: list[str] = ["http://localhost:3000"]
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    worker_enabled: bool = True
    worker_interval_seconds: float = Field(default=3, ge=0.1)
    max_notification_attempts: int = Field(default=8, ge=1, le=20)
    max_daily_chat_requests: int = Field(default=100, ge=1)
    max_concurrent_chats: int = Field(default=2, ge=1, le=8)
    session_days: int = Field(default=7, ge=1, le=30)
    conversation_retention_days: int = Field(default=30, ge=1, le=30)
    lead_retention_days: int = Field(default=180, ge=1, le=180)
    business_file: Path = Path(__file__).with_name("business.json")

    @model_validator(mode="after")
    def production_requirements(self):
        if "*" in self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS must list specific origins")
        if self.environment == "production":
            if not self.worker_enabled:
                raise ValueError("The notification worker must be enabled in production")
            for key in ("session_secret", "admin_token"):
                if len(getattr(self, key).get_secret_value()) < 32:
                    raise ValueError(f"{key.upper()} must contain at least 32 random characters")
            if not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required in production")
            if not self.telegram_bot_token.get_secret_value() or not self.telegram_chat_id:
                raise ValueError("Telegram configuration is required in production")
            if not self.allowed_origins or any(not o.startswith("https://") for o in self.allowed_origins):
                raise ValueError("Production requires explicit HTTPS website origins")
            mount = self.railway_volume_mount_path
            if (
                not mount
                or not mount.is_dir()
                or not self.database_path.resolve().is_relative_to(mount.resolve())
            ):
                raise ValueError("DATABASE_PATH must be inside the attached RAILWAY_VOLUME_MOUNT_PATH")
        return self
