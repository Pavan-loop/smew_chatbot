from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  model_config = SettingsConfigDict(env_file=".env", extra="ignore")
  openai_api: str
  chat_model: str = "gpt-4o-mini"
  extractor_model: str = ""            # empty = same as chat_model
  extractor_timeout_seconds: float = 8.0
  chat_temperature: float = 0.4
  openai_api_base: str = "https://api.openai.com/v1"
  llm_timout_seconds: float = 30.0
  allowed_origins: list[str] = ["http://localhost:3000"]
  telegram_bot_token: str = ""
  telegram_chat_id: str = ""
  debug_token: str = ""                # empty = debug endpoints disabled

@lru_cache()
def get_settings() -> Settings:
  return Settings()

settings = get_settings()