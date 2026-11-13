from math import log2

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 60
    otp_mode: str = "mock"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    cors_origins: str = "http://localhost:5173"
    seed_on_start: bool = False
    env: str = "development"

    @model_validator(mode="after")
    def require_production_jwt_secret(self):
        if self.env.lower() in {"prod", "production"}:
            secret = self.jwt_secret.strip()
            known_defaults = {
                "dev-only-change-me",
                "change-me",
                "replace-with-a-long-random-secret",
                "your-secret-key",
                "secret",
                "password",
            }
            entropy = -sum(
                (count / len(secret)) * log2(count / len(secret))
                for count in (secret.count(char) for char in set(secret))
            ) if secret else 0
            if secret.lower() in known_defaults or len(secret) < 32 or entropy < 3.5:
                raise ValueError("JWT_SECRET must be a strong, non-default value of at least 32 characters in production")
        return self


settings = Settings()
