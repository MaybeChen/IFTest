from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from browser_ai_test.browser.file_upload import upload_case_file
from browser_ai_test.browser.playwright_steps import execute_playwright_steps
from browser_ai_test.browser.stream_monitor import StreamMonitor
from browser_ai_test.config import SystemConfig, UploadConfig, WorkflowConfig
from browser_ai_test.models import UIExecutionResult, WorkflowRun, TestCase

logger = logging.getLogger(__name__)


class FixedWorkflowError(RuntimeError):
    """A deterministic Playwright workflow step failed."""


class FixedPlaywrightExecutor:
    """Run the configured deterministic Playwright QA workflow."""

    def __init__(
        self,
        page: Any,
        monitor: StreamMonitor,
        system: SystemConfig,
        upload: UploadConfig,
        workflow: WorkflowConfig,
        default_timeout: float,
        prepare_case: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.page = page
        self.monitor = monitor
        self.system = system
        self.upload = upload
        self.workflow = workflow
        self.default_timeout = default_timeout
        self.prepare_case = prepare_case

    async def initialize(self) -> None:
        await self.page.goto(self.system.url, wait_until="domcontentloaded")
        await self._login_if_needed()
        await execute_playwright_steps(
            self.page, self.workflow.setup_steps, self.system.iframe_selector,
            self.workflow.step_interval_seconds,
        )

    async def execute(self, case: TestCase) -> WorkflowRun:
        started = time.monotonic()
        steps = 0
        try:
            await self._wait_case_ready(case.id)
            if self.prepare_case:
                await self.prepare_case()
            if self.workflow.before_case_steps:
                await execute_playwright_steps(
                    self.page,
                    self.workflow.before_case_steps,
                    self.system.iframe_selector,
                    self.workflow.step_interval_seconds,
                )
                steps += len(self.workflow.before_case_steps)
            if case.file:
                logger.info("Case %s: uploading file %r", case.id, case.file)
                await upload_case_file(
                    self.page, case.file, self.upload, self.system.iframe_selector
                )
                steps += 1
                await self._pause()
                if self.workflow.after_upload_steps:
                    await execute_playwright_steps(
                        self.page,
                        self.workflow.after_upload_steps,
                        self.system.iframe_selector,
                        self.workflow.step_interval_seconds,
                    )
                    steps += len(self.workflow.after_upload_steps)
                    await self._pause()
            root = self._root()
            question_locator = root.locator(self.workflow.question_selector)
            if self.workflow.question_nth is not None:
                question_locator = question_locator.nth(self.workflow.question_nth)
            logger.info(
                "Case %s: filling question via selector=%r nth=%r",
                case.id, self.workflow.question_selector, self.workflow.question_nth,
            )
            await question_locator.fill(
                case.question, timeout=self.workflow.ui_timeout_ms
            )
            steps += 1
            await self._pause()
            protocol = case.stream.protocol or self.monitor.target_protocol
            self.monitor.arm(protocol)
            logger.info("Case %s: clicking send selector=%r", case.id, self.workflow.send_selector)
            await root.locator(self.workflow.send_selector).click(
                timeout=self.workflow.ui_timeout_ms
            )
            steps += 1
            await self.monitor.wait_done(case.timeout_seconds or self.default_timeout)
            answer = await root.locator(self.workflow.answer_selector).inner_text(
                timeout=self.workflow.ui_timeout_ms
            )
            steps += 1
            return WorkflowRun(
                result=UIExecutionResult(
                    answer=answer, page_ok=True, reason="固定 Playwright 流程执行成功"
                ),
                steps=steps,
                duration_seconds=time.monotonic() - started,
            )
        finally:
            # A timeout or selector error must not leave input/attachments behind
            # for the next serial Case.
            await self._refresh()

    async def _pause(self) -> None:
        if self.workflow.step_interval_seconds:
            await asyncio.sleep(self.workflow.step_interval_seconds)

    def _root(self) -> Any:
        if self.workflow.target == "main":
            return self.page
        if not self.system.iframe_selector:
            raise FixedWorkflowError(
                "workflow.target=iframe 时必须配置 system.iframe_selector"
            )
        return self.page.frame_locator(self.system.iframe_selector)

    async def _login_if_needed(self) -> None:
        login = self.workflow.login
        if not login.enabled:
            return
        detector = self.page.locator(login.detect_selector or login.username_selector)
        if not await detector.is_visible(timeout=login.timeout_ms):
            return
        username = os.getenv(login.username_env)
        password = os.getenv(login.password_env)
        if not username or not password:
            raise FixedWorkflowError(
                f"登录界面可见，但环境变量 {login.username_env}/{login.password_env} 未设置"
            )
        await self.page.locator(login.username_selector).fill(
            username, timeout=login.timeout_ms
        )
        await self._pause()
        await self.page.locator(login.password_selector).fill(
            password, timeout=login.timeout_ms
        )
        await self._pause()
        await self.page.locator(login.submit_selector).click(timeout=login.timeout_ms)
        await self._pause()

    async def _refresh(self) -> None:
        if self.workflow.refresh_action == "none":
            logger.info("Case cleanup: refresh disabled")
            return
        if self.workflow.refresh_action == "reload":
            logger.info("Case cleanup: reloading page")
            await self.page.reload(wait_until="domcontentloaded")
        elif self.workflow.refresh_action == "iframe_reload":
            await self._reload_iframe()
        else:
            if not self.workflow.refresh_selector:
                raise FixedWorkflowError(
                    "workflow.refresh_action=click 时必须配置 refresh_selector"
                )
            logger.info(
                "Case cleanup: clicking refresh selector=%r",
                self.workflow.refresh_selector,
            )
            await self._root().locator(self.workflow.refresh_selector).click(
                timeout=self.workflow.ui_timeout_ms
            )
        if self.workflow.after_refresh_steps:
            logger.info("Case cleanup: restoring QA UI after refresh")
            await execute_playwright_steps(
                self.page,
                self.workflow.after_refresh_steps,
                self.system.iframe_selector,
                self.workflow.step_interval_seconds,
            )
        await self._wait_case_ready("next")
        logger.info("Case cleanup: refresh completed; next Case may start")

    async def _reload_iframe(self) -> None:
        """Reload only the QA iframe without losing the selected product/API."""
        selector = self.system.iframe_selector
        if not selector:
            raise FixedWorkflowError(
                "workflow.refresh_action=iframe_reload 时必须配置 system.iframe_selector"
            )
        logger.info("Case cleanup: reloading iframe selector=%r", selector)
        try:
            handle = await self.page.locator(selector).element_handle(
                timeout=self.workflow.ui_timeout_ms
            )
            if handle is None:
                raise FixedWorkflowError(f"未找到 iframe: {selector!r}")
            frame = await handle.content_frame()
            if frame is None:
                raise FixedWorkflowError(f"元素不是可用 iframe: {selector!r}")
            await frame.reload(
                wait_until="domcontentloaded", timeout=self.workflow.ui_timeout_ms
            )
        except FixedWorkflowError:
            raise
        except Exception as exc:
            raise FixedWorkflowError(f"刷新 iframe {selector!r} 失败: {exc}") from exc

    async def _wait_case_ready(self, case_id: str) -> None:
        selector = self.workflow.case_ready_selector
        if not selector:
            return
        logger.info("Case %s: waiting for QA UI selector=%r", case_id, selector)
        try:
            await self._root().locator(selector).wait_for(
                state="visible", timeout=self.workflow.ui_timeout_ms
            )
        except Exception as exc:
            raise FixedWorkflowError(
                f"问答界面未就绪，selector={selector!r}: {exc}"
            ) from exc
