"""
Конфигурация единого backend-сервиса (API Gateway / BFF).
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WineHackathon Backend API"
    app_version: str = "2.0.0"
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "wine_hackathon_super_secret_jwt_key_32_chars")
    jwt_algorithm: str = "HS256"

    # Redis
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str | None = os.getenv("REDIS_PASSWORD", None)

    # S3 Storage
    s3_endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    s3_access_key: str = os.getenv("MINIO_ROOT_USER", "minio_admin")
    s3_secret_key: str = os.getenv("MINIO_ROOT_PASSWORD", "minio_secure_password_123")
    s3_scans_bucket: str = os.getenv("S3_SCANS_BUCKET", "wine-scans")
    s3_catalog_bucket: str = os.getenv("S3_CATALOG_BUCKET", "wine-catalog")

    # Sommelier & ML Services URLs
    sommelier_service_url: str = os.getenv("SOMMELIER_SERVICE_URL", "http://sommelier:8001")
    ml_service_url: str = os.getenv("ML_SERVICE_URL", "http://ml:8002")

    # Rate limiting for anonymous users
    anon_scan_limit: int = 5
    anon_scan_ttl_seconds: int = 86400  # 24 часа

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
