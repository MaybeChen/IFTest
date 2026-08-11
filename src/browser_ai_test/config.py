from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import PlaywrightStep, Protocol, TestCase


class BrowserConfig(BaseModel):
    cdp_url: str = "http://127.0.0.1:9222"
    headless: bool = False
    cdp_timeout_seconds: float = Field(default=10, gt=0)
    bypass_proxy_for_loopback: bool = True


class SystemConfig(BaseModel):
    url: str
    iframe_hint: str = "business iframe"
    iframe_selector: str | None = None


class UploadConfig(BaseModel):
    directory: Path = Path("data/uploads")
    input_selector: str = "input[type='file']"
    trigger_selector: str | None = None
    target: Literal["main", "iframe", "auto"] = "auto"
    timeout_ms: float = Field(default=10_000, gt=0)


class LoginConfig(BaseModel):
    enabled: bool = False
    username_env: str = "USER_NAME"
    password_env: str = "USER_PASSWORD"
    username_selector: str = "input[placeholder='w3账号']"
    password_selector: str = "input[type='password']"
    submit_selector: str = "button:has-text('登录')"
    detect_selector: str | None = None
    timeout_ms: float = Field(default=10_000, gt=0)


class WorkflowConfig(BaseModel):
    login: LoginConfig = Field(default_factory=LoginConfig)
    setup_steps: list[PlaywrightStep] = Field(default_factory=list)
    before_case_steps: list[PlaywrightStep] = Field(default_factory=list)
    after_upload_steps: list[PlaywrightStep] = Field(default_factory=list)
    question_selector: str = "textarea"
    question_nth: int | None = None
    send_selector: str = "button[type='submit']"
    answer_selector: str = "[data-testid='answer']"
    target: Literal["main", "iframe"] = "iframe"
    refresh_action: Literal["reload", "click", "none"] = "reload"
    refresh_selector: str | None = None
    ui_timeout_ms: float = Field(default=10_000, gt=0)
    step_interval_seconds: float = Field(default=1, ge=0)


class ReportConfig(BaseModel):
    html_directory: Path = Path("reports")


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


class AppConfig(BaseModel):
    browser: BrowserConfig
    system: SystemConfig
    upload: UploadConfig = Field(default_factory=UploadConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    stream: StreamConfig
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)


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
