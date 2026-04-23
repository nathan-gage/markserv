from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PYTHON_RELOAD_ENV_VAR = "MARKSERV_PYTHON_RELOAD"
TARGET_ENV_VAR = "MARKSERV_TARGET"


class MarkservSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    python_reload: bool = Field(default=False, validation_alias=PYTHON_RELOAD_ENV_VAR)
    target: Path | None = Field(default=None, validation_alias=TARGET_ENV_VAR)


def load_settings() -> MarkservSettings:
    return MarkservSettings()


def python_reload_enabled() -> bool:
    return load_settings().python_reload


def target_from_env() -> Path | None:
    return load_settings().target
