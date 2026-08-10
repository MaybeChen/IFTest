from __future__ import annotations

import json
from typing import Any

from browser_ai_test.browser.stream_monitor import StreamMonitor, StreamMonitorError, StreamTimeoutError
from browser_ai_test.models import Protocol


def create_monitor_tools(monitor: StreamMonitor) -> Any:
    """Build case-local browser-use Tools; no mutable monitor is global."""
    from browser_use import ActionResult, Tools

    tools = Tools()

    @tools.action(description="点击发送之前准备并清空 CDP 流监听器。")
    async def arm_stream_monitor(protocol: Protocol = "auto") -> ActionResult:
        return ActionResult(extracted_content=monitor.arm(protocol))

    @tools.action(description="点击发送后等待 CDP 确认业务流完成；不得跳过或用 sleep 替代。")
    async def wait_stream_done(timeout_seconds: int) -> ActionResult:
        try:
            result = await monitor.wait_done(timeout_seconds)
            return ActionResult(extracted_content=json.dumps(result.model_dump(), ensure_ascii=False))
        except (StreamTimeoutError, StreamMonitorError) as exc:
            return ActionResult(error=str(exc))

    return tools
