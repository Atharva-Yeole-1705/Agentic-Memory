from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Use a hosted MongoDB Atlas deployment; no local MongoDB process is required.
    mongodb_uri: str
    mongodb_database: str = "agentic_memory"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    allowed_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
