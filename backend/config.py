from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Use a hosted MongoDB Atlas deployment; no local MongoDB process is required.
    mongodb_uri: str
    mongodb_database: str = "agentic_memory"
    mongodb_vector_index: str = "memory_vector_index"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    # Conservative limits for an 8K Groq TPM account. Values are configurable in .env.
    groq_window_token_budget: int = 7000
    groq_max_input_chars: int = 18_000
    groq_answer_max_tokens: int = 500
    groq_memory_max_tokens: int = 180
    voyage_api_key: str | None = None
    voyage_embedding_model: str = "voyage-3.5-lite"
    voyage_embedding_dimensions: int = 1024
    allowed_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
