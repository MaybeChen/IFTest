import asyncio

import pytest

from browser_ai_test.browser.playwright_steps import (
    PlaywrightStepError,
    execute_playwright_steps,
)
from browser_ai_test.models import PlaywrightStep


class FakeLocator:
    def __init__(self, selector, calls):
        self.selector = selector
        self.calls = calls

    def __getattr__(self, action):
        async def execute(*args, **kwargs):
            self.calls.append((self.selector, action, args, kwargs))
        return execute

    def nth(self, index):
        return FakeLocator(f"{self.selector}:nth({index})", self.calls)


class FakeRoot:
    def __init__(self, calls, prefix="main"):
        self.calls = calls
        self.prefix = prefix

    def locator(self, selector):
        return FakeLocator(f"{self.prefix}:{selector}", self.calls)

    def get_by_text(self, text, **kwargs):
        return FakeLocator(f"{self.prefix}:text={text}:{kwargs}", self.calls)

    def get_by_role(self, role, **kwargs):
        return FakeLocator(f"{self.prefix}:role={role}:{kwargs}", self.calls)

    def get_by_label(self, label, **kwargs):
        return FakeLocator(f"{self.prefix}:label={label}:{kwargs}", self.calls)

    def get_by_placeholder(self, placeholder, **kwargs):
        return FakeLocator(f"{self.prefix}:placeholder={placeholder}:{kwargs}", self.calls)


class FakePage(FakeRoot):
    def frame_locator(self, selector):
        self.calls.append((selector, "frame_locator", (), {}))
        return FakeRoot(self.calls, f"frame({selector})")


def test_executes_main_and_iframe_steps_in_order():
    calls = []
    page = FakePage(calls)
    steps = [
        PlaywrightStep(action="click", selector="#menu", target="main"),
        PlaywrightStep(action="fill", selector="textarea", value="fixed value"),
        PlaywrightStep(action="select_option", selector="select", value="kb-1"),
        PlaywrightStep(action="wait_visible", selector=".ready", timeout_ms=2500),
    ]

    completed = asyncio.run(execute_playwright_steps(page, steps, "#business-frame"))

    assert completed == [
        "1:click:#menu",
        "2:fill:textarea",
        "3:select_option:select",
        "4:wait_visible:.ready",
    ]
    assert calls[0][0:2] == ("main:#menu", "click")
    assert calls[2][0:2] == ("frame(#business-frame):textarea", "fill")
    assert calls[2][2] == ("fixed value",)
    assert calls[-1][3] == {"state": "visible", "timeout": 2500.0}


def test_iframe_step_requires_explicit_selector():
    with pytest.raises(PlaywrightStepError, match="iframe_selector"):
        asyncio.run(
            execute_playwright_steps(
                FakePage([]),
                [PlaywrightStep(action="click", selector="button")],
                None,
            )
        )


def test_value_action_requires_value():
    with pytest.raises(PlaywrightStepError, match="必须配置 value"):
        asyncio.run(
            execute_playwright_steps(
                FakePage([]),
                [PlaywrightStep(action="press", selector="input", target="main")],
                None,
            )
        )


def test_semantic_locator_and_nth_are_supported():
    calls = []
    steps = [
        PlaywrightStep(
            action="click", target="main", locator_type="role",
            selector="button", name="新增", exact=True, nth=1,
        )
    ]
    asyncio.run(execute_playwright_steps(FakePage(calls), steps, None))
    assert calls[0][0].startswith("main:role=button:")
    assert "'name': '新增'" in calls[0][0]
    assert calls[0][0].endswith(":nth(1)")
