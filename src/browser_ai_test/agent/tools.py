import json
from typing import Any, cast

from browser_ai_test.browser.stream_monitor import StreamMonitor, StreamMonitorError, StreamTimeoutError
from browser_ai_test.browser.playwright_steps import execute_playwright_steps
from browser_ai_test.browser.file_upload import upload_case_file
from browser_ai_test.config import UploadConfig
from browser_ai_test.models import PlaywrightStep, Protocol


def create_monitor_tools(
    monitor: StreamMonitor,
    page: Any,
    playwright_steps: list[PlaywrightStep],
    iframe_selector: str | None,
    case_file: str | None,
    upload_config: UploadConfig,
) -> Any:
    """Build case-local browser-use Tools; no mutable monitor is global."""
    from browser_use import ActionResult, Tools

    tools = Tools()
    upload_completed = False
    playwright_steps_completed = False

    @tools.action(description="上传当前 Case 配置的文件；Case 有 file 时必须且只能调用一次。")
    async def upload_case_attachment() -> ActionResult:
        nonlocal upload_completed
        if not case_file:
            return ActionResult(error="当前 Case 未配置 file，禁止调用上传工具")
        if upload_completed:
            return ActionResult(error="当前 Case 文件已经成功上传，禁止重复上传")
        try:
            uploaded = await upload_case_file(
                page, case_file, upload_config, iframe_selector
            )
            upload_completed = True
            return ActionResult(
                extracted_content=json.dumps(
                    {"uploaded": True, "file_name": uploaded.name}, ensure_ascii=False
                )
            )
        except Exception as exc:
            return ActionResult(error=str(exc))

    @tools.action(description="执行 Case 配置的精确 Playwright 步骤；如有配置必须且只能调用一次。")
    async def run_playwright_steps() -> ActionResult:
        nonlocal playwright_steps_completed
        if not playwright_steps:
            return ActionResult(error="当前 Case 未配置 playwright_steps，禁止调用该工具")
        if playwright_steps_completed:
            return ActionResult(error="当前 Case 的 Playwright 步骤已经成功执行，禁止重复执行")
        try:
            completed = await execute_playwright_steps(page, playwright_steps, iframe_selector)
            playwright_steps_completed = True
            return ActionResult(
                extracted_content=json.dumps({"completed": completed}, ensure_ascii=False)
            )
        except Exception as exc:
            return ActionResult(error=str(exc))

    @tools.action(description="点击发送之前准备并清空 CDP 流监听器。")
    async def arm_stream_monitor(protocol: str = "auto") -> ActionResult:
        # Keep the public action annotation concrete. browser-use 0.11 builds a
        # dynamic AgentOutput model from it and cannot resolve a postponed
        # project-local `Protocol` forward reference.
        if protocol not in {"sse", "websocket", "http", "auto"}:
            return ActionResult(
                error="protocol 必须是 sse、websocket、http 或 auto"
            )
        return ActionResult(
            extracted_content=monitor.arm(cast(Protocol, protocol))
        )

    @tools.action(description="点击发送后等待 CDP 确认业务流完成；不得跳过或用 sleep 替代。")
    async def wait_stream_done(timeout_seconds: int) -> ActionResult:
        try:
            result = await monitor.wait_done(timeout_seconds)
            return ActionResult(extracted_content=json.dumps(result.model_dump(), ensure_ascii=False))
        except (StreamTimeoutError, StreamMonitorError) as exc:
            return ActionResult(error=str(exc))

    return tools
