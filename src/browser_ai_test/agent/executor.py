from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Any

from browser_ai_test.agent.prompts import build_task
from browser_ai_test.agent.tools import create_monitor_tools
from browser_ai_test.browser.session import SharedBrowserSession
from browser_ai_test.config import SystemConfig
from browser_ai_test.models import AgentExecutionResult, TestCase


@dataclass(slots=True)
class AgentRun:
    result: AgentExecutionResult
    steps: int
    duration_seconds: float


class AgentExecutor:
    def __init__(self, session: SharedBrowserSession, system: SystemConfig, default_timeout: float, llm: Any | None = None) -> None:
        self.session = session
        self.system = system
        self.default_timeout = default_timeout
        self.llm = llm

    async def execute(self, case: TestCase) -> AgentRun:
        from browser_use import Agent

        if self.llm is None:
            raise RuntimeError("AgentExecutor 必须注入已配置的模型实例")
        kwargs: dict[str, Any] = {
            "task": build_task(
                case,
                self.system,
                case.stream.protocol or self.session.stream_config.protocol,
                case.timeout_seconds or self.default_timeout,
            ),
            "llm": self.llm,
            "browser_session": self.session.browser_use_session,
            "tools": create_monitor_tools(self.session.monitor),
        }
        signature = inspect.signature(Agent)
        if "output_model_schema" in signature.parameters:
            kwargs["output_model_schema"] = AgentExecutionResult
        elif "output_model" in signature.parameters:
            kwargs["output_model"] = AgentExecutionResult
        else:
            raise RuntimeError("当前 browser-use Agent 缺少结构化输出参数")
        started = time.monotonic()
        history = await Agent(**kwargs).run()
        duration = time.monotonic() - started
        raw = getattr(history, "structured_output", None)
        if callable(raw):
            raw = raw()
        if raw is None:
            raise RuntimeError("Agent 未返回结构化页面答案")
        result = raw if isinstance(raw, AgentExecutionResult) else AgentExecutionResult.model_validate(raw)
        steps = self._history_metric(history, "number_of_steps", 0)
        history_duration = self._history_metric(history, "total_duration_seconds", duration)
        return AgentRun(result=result, steps=int(steps), duration_seconds=float(history_duration))

    @staticmethod
    def _history_metric(history: Any, name: str, default: Any) -> Any:
        value = getattr(history, name, default)
        return value() if callable(value) else value
