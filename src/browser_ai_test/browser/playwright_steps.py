from __future__ import annotations

import asyncio
import logging
from typing import Any

from browser_ai_test.models import PlaywrightStep

logger = logging.getLogger(__name__)


class PlaywrightStepError(RuntimeError):
    """An explicitly configured deterministic browser action failed."""


async def execute_playwright_steps(
    page: Any,
    steps: list[PlaywrightStep],
    iframe_selector: str | None,
    interval_seconds: float = 0,
) -> list[str]:
    """Execute a small, auditable Playwright action DSL in declared order."""
    completed: list[str] = []
    for index, step in enumerate(steps, start=1):
        if step.target == "iframe":
            if not iframe_selector:
                raise PlaywrightStepError(
                    f"Playwright step {index} target=iframe，但 system.iframe_selector 未配置"
                )
            root = page.frame_locator(iframe_selector)
        else:
            root = page
        locator = _resolve_locator(root, step)
        logger.info(
            "Playwright step %s/%s start: action=%s target=%s locator=%s selector=%r",
            index, len(steps), step.action, step.target, step.locator_type, step.selector,
        )
        try:
            if step.action == "click":
                await locator.click(timeout=step.timeout_ms)
            elif step.action == "fill":
                await locator.fill(_required_value(step, index), timeout=step.timeout_ms)
            elif step.action == "select_option":
                await locator.select_option(_required_value(step, index), timeout=step.timeout_ms)
            elif step.action == "check":
                await locator.check(timeout=step.timeout_ms)
            elif step.action == "press":
                await locator.press(_required_value(step, index), timeout=step.timeout_ms)
            elif step.action == "wait_visible":
                await locator.wait_for(state="visible", timeout=step.timeout_ms)
        except PlaywrightStepError:
            raise
        except Exception as exc:
            raise PlaywrightStepError(
                f"Playwright step {index} 执行失败: {step.action} {step.selector!r}: {exc}"
            ) from exc
        completed.append(f"{index}:{step.action}:{step.selector}")
        logger.info(
            "Playwright step %s/%s completed: action=%s selector=%r",
            index, len(steps), step.action, step.selector,
        )
        if interval_seconds and index < len(steps):
            # UI pacing only; never used to decide whether a stream completed.
            await asyncio.sleep(interval_seconds)
    return completed


def _required_value(step: PlaywrightStep, index: int) -> str:
    if step.value is None:
        raise PlaywrightStepError(
            f"Playwright step {index} action={step.action} 必须配置 value"
        )
    return step.value


def _resolve_locator(root: Any, step: PlaywrightStep) -> Any:
    if step.locator_type == "text":
        locator = root.get_by_text(step.selector, exact=step.exact)
    elif step.locator_type == "role":
        locator = root.get_by_role(step.selector, name=step.name, exact=step.exact)
    elif step.locator_type == "label":
        locator = root.get_by_label(step.selector, exact=step.exact)
    elif step.locator_type == "placeholder":
        locator = root.get_by_placeholder(step.selector, exact=step.exact)
    else:
        locator = root.locator(step.selector)
    return locator.nth(step.nth) if step.nth is not None else locator
