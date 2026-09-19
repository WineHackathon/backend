"""
Конфигурация специализированного сервиса AI-Сомелье.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WineHackathon AI Sommelier Service"
    app_version: str = "2.0.0"

    # LLM Settings (OpenRouter)
    llm_api_base_url: str = os.getenv("LLM_API_BASE_URL", "https://openrouter.ai/api/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "google/gemini-2.0-flash-exp:free")

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str | None = os.getenv("REDIS_PASSWORD", None)

    # Database
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_user: str = os.getenv("POSTGRES_USER", "wine_admin")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "change_this_in_production")
    postgres_db: str = os.getenv("POSTGRES_DB", "wine_db")

    # CORS
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
