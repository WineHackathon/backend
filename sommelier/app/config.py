"""
Конфигурация специализированного сервиса AI-Сомелье.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WineHackathon AI Sommelier Service"
    app_version: str = "2.0.0"

    # LLM Settings (OpenRouter)
    llm_api_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model_name: str = "meta-llama/llama-3.3-70b-instruct"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "wine_admin"
    postgres_password: str = "change_this_in_production"
    postgres_db: str = "wine_db"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": False,
    }


settings = Settings()
