from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://commontrace:commontrace@localhost:5432/commontrace"
    redis_url: str = "redis://localhost:6379"
    validation_threshold: int = 2
    app_name: str = "CommonTrace"
    debug: bool = False
    embedding_dimensions: int = 1536
    rate_limit_read_per_minute: int = 60
    rate_limit_write_per_minute: int = 20
    api_key_header_name: str = "X-API-Key"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Temporal decay
    temporal_decay_default_half_life_days: int = 365

    # Consolidation worker
    consolidation_interval_hours: int = 24
    consolidation_stale_age_days: int = 180
    narrative_max_clusters_per_cycle: int = 5


settings = Settings()
