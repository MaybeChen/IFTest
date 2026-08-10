from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import Protocol, TestCase


class BrowserConfig(BaseModel):
    cdp_url: str = "http://localhost:9222"
    headless: bool = False


class SystemConfig(BaseModel):
    url: str
    iframe_hint: str = "business iframe"
    iframe_selector: str | None = None


class StreamConfig(BaseModel):
    protocol: Protocol = "auto"
    url_keywords: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(default=120, gt=0)
    done_markers: list[str] = Field(min_length=1)


class DatabaseConfig(BaseModel):
    path: Path = Path("data/results.db")


class RunnerConfig(BaseModel):
    continue_on_failure: bool = True
    case_interval_seconds: float = Field(default=1, ge=0)
    retry_count: int = Field(default=0, ge=0)


class LoggingConfig(BaseModel):
    level: str = "INFO"


class LLMConfig(BaseModel):
    """Model construction settings without storing credentials in YAML."""

    provider: Literal[
        "browser_use", "openai", "openai_compatible", "anthropic", "google", "custom"
    ] = "browser_use"
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    class_path: str | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    browser: BrowserConfig
    system: SystemConfig
    stream: StreamConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _read_yaml(path: Path) -> dict[str, Any]:
    import yaml

    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    from dotenv import load_dotenv

    load_dotenv()
    data = _read_yaml(Path(path))
    if cdp_url := os.getenv("BROWSER_AI_TEST_CDP_URL"):
        data.setdefault("browser", {})["cdp_url"] = cdp_url
    return AppConfig.model_validate(data)


def load_cases(path: str | Path = "config/cases.yaml") -> list[TestCase]:
    return [TestCase.model_validate(item) for item in _read_yaml(Path(path)).get("cases", [])]
