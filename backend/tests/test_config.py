import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_a_strong_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET must contain at least 32 characters"):
        Settings(env="production", jwt_secret="dev-only-change-me")


def test_development_keeps_the_local_jwt_secret_default():
    assert Settings(_env_file=None, env="development").jwt_secret == "dev-only-change-me"
