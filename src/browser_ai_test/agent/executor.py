from __future__ import annotations

import inspect
import time
from typing import Any

from browser_ai_test.agent.prompts import build_task
from browser_ai_test.agent.tools import create_monitor_tools
from browser_ai_test.browser.session import SharedBrowserSession
from browser_ai_test.config import AgentConfig, SystemConfig, UploadConfig
from browser_ai_test.models import AgentExecutionResult, AgentRun, TestCase


class AgentExecutor:
    def __init__(self, session: SharedBrowserSession, system: SystemConfig, agent: AgentConfig, upload: UploadConfig, default_timeout: float, llm: Any | None = None) -> None:
        self.session = session
        self.system = system
        self.agent_config = agent
        self.upload_config = upload
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
                self.agent_config,
                case.stream.protocol or self.session.stream_config.protocol,
                case.timeout_seconds or self.default_timeout,
            ),
            "llm": self.llm,
            "browser_session": self.session.browser_use_session,
            "tools": create_monitor_tools(
                self.session.monitor,
                self.session.page,
                case.playwright_steps,
                self.system.iframe_selector,
                case.file,
                self.upload_config,
            ),
        }
        signature = inspect.signature(Agent)
        if "output_model_schema" in signature.parameters:
            kwargs["output_model_schema"] = AgentExecutionResult
        elif "output_model" in signature.parameters:
            kwargs["output_model"] = AgentExecutionResult
        else:
            raise RuntimeError("当前 browser-use Agent 缺少结构化输出参数")
        started = time.monotonic()
        browser_agent = Agent(**kwargs)
        run_signature = inspect.signature(browser_agent.run)
        if "max_steps" not in run_signature.parameters:
            raise RuntimeError("当前 browser-use Agent.run 不支持 max_steps 参数")
        history = await browser_agent.run(max_steps=self.agent_config.max_steps)
        duration = time.monotonic() - started
        raw = getattr(history, "structured_output", None)
        if callable(raw):
            raw = raw()
        if raw is None:
            history_errors = self._history_metric(history, "errors", []) or []
            detail = "; ".join(str(error) for error in history_errors if error)
            suffix = f"；Browser Use errors: {detail}" if detail else ""
            raise RuntimeError(f"Agent 未返回结构化页面答案{suffix}")
        result = raw if isinstance(raw, AgentExecutionResult) else AgentExecutionResult.model_validate(raw)
        steps = self._history_metric(history, "number_of_steps", 0)
        history_duration = self._history_metric(history, "total_duration_seconds", duration)
        return AgentRun(result=result, steps=int(steps), duration_seconds=float(history_duration))

    @staticmethod
    def _history_metric(history: Any, name: str, default: Any) -> Any:
        value = getattr(history, name, default)
        return value() if callable(value) else value
