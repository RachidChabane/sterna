"""Configuration settings for the User Preferences service."""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union


class Settings(BaseSettings):
    """Application settings."""

    # Service info
    app_name: str = "User Preferences Service"
    version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str

    # JWT Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15

    # CORS - can be a string (comma-separated) or list
    cors_origins: Union[str, List[str]] = "http://localhost:3000,http://localhost:5173,http://localhost:8000"

    # Allowed CORS methods and headers
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    cors_allow_credentials: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
