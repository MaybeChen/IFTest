from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from browser_ai_test.agent.executor import AgentExecutor
from browser_ai_test.agent.model_factory import create_llm
from browser_ai_test.browser.session import SharedBrowserSession
from browser_ai_test.config import AppConfig
from browser_ai_test.metrics.collector import MetricsCollector
from browser_ai_test.metrics.database import ResultsDatabase
from browser_ai_test.models import CaseResult, ErrorType, TestCase
from browser_ai_test.report.console import render_case, render_summary
from browser_ai_test.validator import get_validator

logger = logging.getLogger(__name__)


class TestRunner:
    def __init__(self, config: AppConfig, database: ResultsDatabase, session_factory: type[SharedBrowserSession] = SharedBrowserSession) -> None:
        self.config = config
        self.database = database
        self.session_factory = session_factory

    async def run(self, cases: list[TestCase]) -> tuple[str, MetricsCollector]:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        started = datetime.now(timezone.utc)
        self.database.start_run(run_id, started.isoformat())
        collector = MetricsCollector()
        try:
            llm = create_llm(self.config.llm)
            async with self.session_factory(self.config.browser, self.config.stream) as session:
                executor = AgentExecutor(
                    session,
                    self.config.system,
                    self.config.agent,
                    self.config.stream.timeout_seconds,
                    llm=llm,
                )
                for index, case in enumerate(cases, 1):
                    result = await self._run_case(run_id, case, executor, session)
                    collector.add(result)
                    self.database.save_case(result)
                    render_case(result, index, len(cases))
                    if not result.passed and not self.config.runner.continue_on_failure:
                        break
                    if index < len(cases) and self.config.runner.case_interval_seconds:
                        await asyncio.sleep(self.config.runner.case_interval_seconds)
        finally:
            passed = sum(item.passed for item in collector.results)
            self.database.finish_run(run_id, datetime.now(timezone.utc).isoformat(), len(collector.results), passed)
        render_summary(run_id, collector.statistics())
        return run_id, collector

    async def _run_case(self, run_id: str, case: TestCase, executor: AgentExecutor, session: SharedBrowserSession) -> CaseResult:
        started = datetime.now(timezone.utc)
        protocol = case.stream.protocol or self.config.stream.protocol
        session.monitor.arm(protocol)
        answer = ""
        agent_ok = network_ok = answer_ok = False
        error_type: ErrorType | None = None
        detail: str | None = None
        steps = 0
        duration: float | None = None
        try:
            agent_run = await executor.execute(case)
            answer = agent_run.result.answer
            steps, duration = agent_run.steps, agent_run.duration_seconds
            agent_ok = agent_run.result.page_ok
            network_ok = session.monitor.done_event.is_set() and not session.monitor.network_error and session.monitor.done_ts is not None
            validation = get_validator(case.expected.type, case.expected.match_mode).validate(answer, case.expected.values)
            answer_ok = validation.passed
            if not agent_ok:
                error_type, detail = ErrorType.PAGE_ERROR, agent_run.result.reason
            elif not network_ok:
                error_type = ErrorType.NETWORK_ERROR if session.monitor.network_error else (ErrorType.STREAM_NOT_FOUND if not session.monitor.request_ids else ErrorType.STREAM_TIMEOUT)
                detail = session.monitor.network_error or "CDP 未确认业务完成"
            elif not answer_ok:
                error_type, detail = ErrorType.ANSWER_VALIDATION_FAILED, validation.reason
        except Exception as exc:
            logger.exception("Case %s execution failed", case.id)
            detail = str(exc)
            if not session.monitor.request_ids:
                error_type = ErrorType.STREAM_NOT_FOUND if session.monitor.armed else ErrorType.AGENT_ERROR
            elif session.monitor.network_error:
                error_type = ErrorType.NETWORK_ERROR
            elif not session.monitor.done_event.is_set():
                error_type = ErrorType.STREAM_TIMEOUT
            else:
                error_type = ErrorType.AGENT_ERROR
        request_start = session.monitor.request_start_ts
        first = session.monitor.first_message_ts
        done = session.monitor.done_ts
        ttft = (first - request_start) * 1000 if first is not None and request_start is not None else None
        stream_total = (done - request_start) * 1000 if done is not None and request_start is not None else None
        passed = agent_ok and network_ok and answer_ok
        return CaseResult(
            run_id=run_id, case_id=case.id, case_name=case.name, started_at=started,
            finished_at=datetime.now(timezone.utc), passed=passed, agent_ok=agent_ok,
            network_ok=network_ok, answer_ok=answer_ok, protocol=session.monitor.detected_protocol or protocol,
            ttft_ms=ttft, stream_total_ms=stream_total, agent_total_seconds=duration,
            agent_steps=steps, question=case.question, answer=answer,
            error_type=None if passed else (error_type or ErrorType.UNKNOWN), error_detail=detail,
        )
