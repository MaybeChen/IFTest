from __future__ import annotations

from typing import Any

from browser_ai_test.models import PlaywrightStep


class PlaywrightStepError(RuntimeError):
    """An explicitly configured deterministic browser action failed."""


async def execute_playwright_steps(
    page: Any,
    steps: list[PlaywrightStep],
    iframe_selector: str | None,
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
        locator = root.locator(step.selector)
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
    return completed


def _required_value(step: PlaywrightStep, index: int) -> str:
    if step.value is None:
        raise PlaywrightStepError(
            f"Playwright step {index} action={step.action} 必须配置 value"
        )
    return step.value
