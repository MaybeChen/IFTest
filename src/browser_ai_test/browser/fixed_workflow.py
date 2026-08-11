from __future__ import annotations

import os
import time
from typing import Any

from browser_ai_test.browser.file_upload import upload_case_file
from browser_ai_test.browser.playwright_steps import execute_playwright_steps
from browser_ai_test.browser.stream_monitor import StreamMonitor
from browser_ai_test.config import SystemConfig, UploadConfig, WorkflowConfig
from browser_ai_test.models import UIExecutionResult, WorkflowRun, TestCase


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
    ) -> None:
        self.page = page
        self.monitor = monitor
        self.system = system
        self.upload = upload
        self.workflow = workflow
        self.default_timeout = default_timeout

    async def initialize(self) -> None:
        await self.page.goto(self.system.url, wait_until="domcontentloaded")
        await self._login_if_needed()
        await execute_playwright_steps(
            self.page, self.workflow.setup_steps, self.system.iframe_selector
        )

    async def execute(self, case: TestCase) -> WorkflowRun:
        started = time.monotonic()
        steps = 0
        try:
            if case.file:
                await upload_case_file(
                    self.page, case.file, self.upload, self.system.iframe_selector
                )
                steps += 1
            root = self._root()
            await root.locator(self.workflow.question_selector).fill(
                case.question, timeout=self.workflow.ui_timeout_ms
            )
            steps += 1
            protocol = case.stream.protocol or self.monitor.target_protocol
            self.monitor.arm(protocol)
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
        await self.page.locator(login.password_selector).fill(
            password, timeout=login.timeout_ms
        )
        await self.page.locator(login.submit_selector).click(timeout=login.timeout_ms)

    async def _refresh(self) -> None:
        if self.workflow.refresh_action == "none":
            return
        if self.workflow.refresh_action == "reload":
            await self.page.reload(wait_until="domcontentloaded")
            return
        if not self.workflow.refresh_selector:
            raise FixedWorkflowError(
                "workflow.refresh_action=click 时必须配置 refresh_selector"
            )
        await self._root().locator(self.workflow.refresh_selector).click(
            timeout=self.workflow.ui_timeout_ms
        )
