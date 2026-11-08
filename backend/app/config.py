from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


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
        if self.env.lower() in {"prod", "production"} and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters in production")
        return self


settings = Settings()
