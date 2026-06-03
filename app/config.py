from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Дефолти дозволяють запустити Docker Compose без локального .env.
    # .env потрібен тільки тоді, коли треба перевизначити значення під свою машину.
    database_url: str = "postgresql://store_user:store_password@postgres:5432/store_db"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_purchase_queue: str = "purchase_events"
    cors_origins: str = "*"
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20
    api_workers: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
