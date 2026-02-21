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


settings = Settings()
