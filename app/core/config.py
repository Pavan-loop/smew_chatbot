from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
  model_config = SettingsConfigDict(env_file=".env", extra="ignore")
  openai_api: str
  chat_model: str = "gpt-4o-mini"
  openai_api_base: str = "https://api.openai.com/v1"
  llm_timout_seconds: float = 30.0
  allowed_origins: list[str] = ["http://localhost:3000"]

@lru_cache()
def get_settings() -> Settings:
  return Settings()

settings = get_settings()