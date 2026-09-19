import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ML Service configuration."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WineHackathon ML Worker"

    # Redis Broker & Streams
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")
    tasks_stream: str = "ml:tasks:recognition"
    consumer_group: str = "ml_group"
    consumer_name: str = Field(default_factory=lambda: f"worker_{os.getpid()}")
    response_channel_prefix: str = "ml:results:"

    # MinIO / S3 Storage
    s3_endpoint_url: str = Field(default="http://minio:9000", alias="S3_ENDPOINT_URL")
    s3_scans_bucket: str = Field(default="wine-scans", alias="S3_SCANS_BUCKET")
    s3_catalog_bucket: str = Field(default="wine-catalog", alias="S3_CATALOG_BUCKET")
    s3_access_key: str = Field(default="minio_admin", alias="MINIO_ROOT_USER")
    s3_secret_key: str = Field(default="minio_secure_password_123", alias="MINIO_ROOT_PASSWORD")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    # Catalog Service for Index Bootstrap
    catalog_service_url: str = Field(default="http://catalog-service:8000", alias="CATALOG_SERVICE_URL")

    # Local Index File & Integrity
    index_cache_file: str = "data/wine_embeddings_index.npz"
    index_hmac_secret: str = Field(default="wine_ml_index_integrity_secret_key_v1", alias="INDEX_HMAC_SECRET")


settings = Settings()
