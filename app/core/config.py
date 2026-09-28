from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:55433/app"
    test_database_url: str = "postgresql+psycopg://app:app@localhost:55433/app_test"
    redis_url: str = "redis://localhost:56380/0"
    test_redis_url: str = "redis://localhost:56380/1"
    task_webhook_secret: str = Field(min_length=1)
    app_root_path: str = ""
    click_merchant_id: str | None = None
    click_service_id: str | None = None
    click_secret_key: str | None = None
    click_merchant_user_id: str | None = None
    click_return_url: str | None = None

    @model_validator(mode="after")
    def validate_click_credentials(self) -> "Settings":
        credentials = (
            self.click_merchant_id,
            self.click_service_id,
            self.click_secret_key,
            self.click_merchant_user_id,
        )
        if any(credentials) and not all(credentials):
            raise ValueError(
                "CLICK_MERCHANT_ID, CLICK_SERVICE_ID, CLICK_SECRET_KEY, and "
                "CLICK_MERCHANT_USER_ID must be configured together"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
