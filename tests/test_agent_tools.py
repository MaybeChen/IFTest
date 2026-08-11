import asyncio
import inspect
import sys
import types

from browser_ai_test.agent.tools import create_monitor_tools
from browser_ai_test.browser.stream_monitor import StreamMonitor
from browser_ai_test.config import UploadConfig


class FakeActionResult:
    def __init__(self, extracted_content=None, error=None):
        self.extracted_content = extracted_content
        self.error = error


class FakeTools:
    def __init__(self):
        self.actions = {}

    def action(self, description):
        def register(function):
            self.actions[function.__name__] = function
            return function
        return register


def make_tools(monkeypatch):
    module = types.ModuleType("browser_use")
    module.ActionResult = FakeActionResult
    module.Tools = FakeTools
    monkeypatch.setitem(sys.modules, "browser_use", module)
    return create_monitor_tools(
        StreamMonitor(["/stream"], ["[DONE]"]),
        page=object(),
        playwright_steps=[],
        iframe_selector=None,
        case_file=None,
        upload_config=UploadConfig(),
    )


def test_arm_action_exposes_concrete_string_annotation(monkeypatch):
    tools = make_tools(monkeypatch)
    signature = inspect.signature(tools.actions["arm_stream_monitor"])
    assert signature.parameters["protocol"].annotation is str
    assert signature.return_annotation is FakeActionResult


def test_arm_action_validates_protocol_before_monitor(monkeypatch):
    tools = make_tools(monkeypatch)
    invalid = asyncio.run(tools.actions["arm_stream_monitor"]("invalid"))
    valid = asyncio.run(tools.actions["arm_stream_monitor"]("sse"))
    assert "protocol 必须是" in invalid.error
    assert "网络监听已经准备完成" in valid.extracted_content
