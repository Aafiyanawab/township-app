from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_requires_a_strong_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET must be a strong, non-default value"):
        Settings(env="production", jwt_secret="dev-only-change-me")

    with pytest.raises(ValidationError, match="JWT_SECRET must be a strong, non-default value"):
        Settings(env="production", jwt_secret="a" * 64)

    with pytest.raises(ValidationError, match="JWT_SECRET must be a strong, non-default value"):
        Settings(env="production", jwt_secret="replace-with-a-long-random-secret")


def test_development_keeps_the_local_jwt_secret_default():
    assert Settings(_env_file=None, env="development").jwt_secret == "dev-only-change-me"


def test_env_example_contains_variable_names_without_values():
    example = Path(__file__).resolve().parents[2] / ".env.example"
    assignments = [line for line in example.read_text().splitlines() if line and not line.startswith("#")]
    assert assignments
    assert all(line.endswith("=") for line in assignments)
