from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Protocol = Literal["sse", "websocket", "http", "auto"]


class ErrorType(StrEnum):
    AGENT_ERROR = "AGENT_ERROR"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    STREAM_NOT_FOUND = "STREAM_NOT_FOUND"
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    ANSWER_VALIDATION_FAILED = "ANSWER_VALIDATION_FAILED"
    PAGE_ERROR = "PAGE_ERROR"
    UNKNOWN = "UNKNOWN"


class ExpectedConfig(BaseModel):
    type: Literal["keyword", "regex", "exact", "json", "llm_judge"]
    values: list[str] = Field(min_length=1)
    match_mode: Literal["all", "any"] = "all"


class CaseStreamConfig(BaseModel):
    protocol: Protocol | None = None


class PlaywrightStep(BaseModel):
    action: Literal["click", "fill", "select_option", "check", "press", "wait_visible"]
    selector: str
    value: str | None = None
    target: Literal["main", "iframe"] = "iframe"
    timeout_ms: float = Field(default=10_000, gt=0)


class TestCase(BaseModel):
    id: str
    name: str
    question: str
    file: str | None = None
    steps: list[str] = Field(default_factory=list)
    playwright_steps: list[PlaywrightStep] = Field(default_factory=list)
    expected: ExpectedConfig
    stream: CaseStreamConfig = Field(default_factory=CaseStreamConfig)
    timeout_seconds: float | None = Field(default=None, gt=0)


class ValidationResult(BaseModel):
    passed: bool
    reason: str


class AgentExecutionResult(BaseModel):
    answer: str
    page_ok: bool
    reason: str


@dataclass(slots=True)
class AgentRun:
    result: AgentExecutionResult
    steps: int
    duration_seconds: float


class StreamResult(BaseModel):
    completed: bool
    protocol: Protocol | None = None
    ttft_ms: float | None = None
    stream_total_ms: float | None = None
    error: str | None = None


class CaseResult(BaseModel):
    run_id: str
    case_id: str
    case_name: str
    started_at: datetime
    finished_at: datetime
    passed: bool
    agent_ok: bool
    network_ok: bool
    answer_ok: bool
    protocol: str | None = None
    ttft_ms: float | None = None
    stream_total_ms: float | None = None
    agent_total_seconds: float | None = None
    agent_steps: int = 0
    question: str
    answer: str = ""
    error_type: ErrorType | None = None
    error_detail: str | None = None

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
