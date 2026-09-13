import os
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")


class Settings(BaseSettings):
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    LOG_LEVEL: str = "info"

    # CORS
    ALLOWED_ORIGINS: str | List[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # AI model settings
    NEWS_API_KEY: str = "your_newsapi_key_here"

    # Verification timeout (seconds)
    VERIFY_TIMEOUT_SECONDS: int = 45

    # Rate limiting
    RATE_LIMIT: str = "10/minute"

    # Retrieval
    RETRIEVAL_TIME_BUDGET_SECONDS: int = 20

    # Streaming Uploads
    MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def validate_production_settings(self) -> None:
        """Enforce strict configuration rules in production mode."""
        if self.ENVIRONMENT.lower() == "production":
            if self.RELOAD:
                raise ValueError("RELOAD must be False in production environments.")
            origins = self.ALLOWED_ORIGINS if isinstance(self.ALLOWED_ORIGINS, list) else [self.ALLOWED_ORIGINS]
            if not origins or "*" in origins:
                raise ValueError("Wildcard or empty ALLOWED_ORIGINS is forbidden in production environments.")



settings = Settings()
