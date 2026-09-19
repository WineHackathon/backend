"""
Конфигурация единого backend-сервиса (API Gateway / BFF).
"""
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WineHackathon Backend API"
    app_version: str = "2.0.0"
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8050",
        "http://127.0.0.1:8050",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Auth & JWT
    jwt_secret_key: str = "wine_hackathon_super_secret_jwt_key_32_chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Upload & Scanner
    max_upload_size_mb: int = 15

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None

    # S3 Storage (FirstVDS / AWS S3 compatible)
    s3_endpoint_url: str = "https://s3.firstvds.ru:443"
    s3_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("S3_ACCESS_KEY", "S3_AWS_ACCESS_KEY_ID"),
    )
    s3_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("S3_SECRET_KEY", "S3_AWS_SECRET_ACCESS_KEY"),
    )
    s3_bucket_name: str = "wine-hack"
    s3_region_name: str = "ru-central-1"
    s3_scans_bucket: str = "wine-hack"
    s3_catalog_bucket: str = "wine-hack"

    # Sommelier & ML Services URLs
    sommelier_service_url: str = "http://sommelier:8001"
    ml_service_url: str = "http://ml:8002"

    # ML Dispatcher Mock Mode (fallback for local dev/frontend without heavy ML worker)
    ml_mock_mode: bool = True

    # Yandex ID OAuth 2.0
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = "http://localhost:8050/api/v1/auth/yandex/callback"

    # Rate limiting for anonymous users
    anon_scan_limit: int = 5
    anon_scan_ttl_seconds: int = 86400  # 24 часа

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": False,
    }


settings = Settings()
