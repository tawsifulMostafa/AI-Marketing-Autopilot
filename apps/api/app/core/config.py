from functools import lru_cache

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "MarketFlow AI API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/v1"

    database_url: str | None = None
    database_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    supabase_url: AnyHttpUrl | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "marketflow-assets"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"
    image_provider: str = "openai"
    image_model: str = "gpt-image-1"

    shopify_api_version: str = "2026-04"
    shopify_store_url: str | None = None
    shopify_access_token: str | None = None
    shopify_client_id: str | None = None
    shopify_client_secret: str | None = None
    shopify_webhook_secret: str | None = None

    woocommerce_consumer_key: str | None = None
    woocommerce_consumer_secret: str | None = None

    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_page_id: str | None = None
    meta_api_version: str = "v21.0"
    meta_default_campaign_status: str = "PAUSED"
    meta_default_ad_status: str = "PAUSED"

    google_ads_developer_token: str | None = None
    google_ads_client_id: str | None = None
    google_ads_client_secret: str | None = None
    google_ads_refresh_token: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)

    @field_validator("supabase_url", mode="before")
    @classmethod
    def normalize_optional_url(cls, value: str | None) -> str | None:
        return value or None

    @property
    def is_database_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
