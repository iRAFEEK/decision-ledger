from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5499/decision_ledger"
    redis_url: str = "redis://localhost:6379"
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    jwt_secret: str = "change-me"
    encryption_key: str = "change-me-32-bytes-long-key-here"


settings = Settings()
