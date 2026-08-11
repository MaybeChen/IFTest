import asyncio
from types import SimpleNamespace

from browser_ai_test.config import AppConfig
from browser_ai_test.models import UIExecutionResult, WorkflowRun, ExpectedConfig, TestCase as CaseModel
from browser_ai_test.runner import TestRunner as Runner


class FakeDatabase:
    def start_run(self, *args): pass
    def save_case(self, result): self.result = result
    def finish_run(self, *args): pass


class FakeSession:
    def __init__(self, browser, stream):
        self.page = object()
        self.monitor = SimpleNamespace(
            done_event=SimpleNamespace(is_set=lambda: True), network_error=None,
            done_ts=2.0, request_start_ts=1.0, first_message_ts=1.2,
            detected_protocol="sse", request_ids={"request"}, target_protocol="sse",
            arm=lambda protocol: None,
        )

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class FakeFixedExecutor:
    initialized = False

    def __init__(self, *args): pass
    async def initialize(self): type(self).initialized = True
    async def execute(self, case):
        return WorkflowRun(UIExecutionResult(answer="标准答案", page_ok=True, reason="ok"), 4, 1.0)


def test_runner_uses_fixed_playwright_workflow(monkeypatch, tmp_path):
    import browser_ai_test.runner as runner_module

    config = AppConfig.model_validate({
        "browser": {}, "system": {"url": "https://test", "iframe_selector": "#frame"},
        "stream": {"url_keywords": ["/stream"], "done_markers": ["[DONE]"]},
        "runner": {"case_interval_seconds": 0},
        "report": {"html_directory": str(tmp_path)},
    })
    case = CaseModel(id="C1", name="case", question="q", expected=ExpectedConfig(type="keyword", values=["答案"]))
    monkeypatch.setattr(runner_module, "FixedPlaywrightExecutor", FakeFixedExecutor)
    monkeypatch.setattr(runner_module, "render_case", lambda *args: None)
    monkeypatch.setattr(runner_module, "render_summary", lambda *args: None)

    _, collector = asyncio.run(Runner(config, FakeDatabase(), FakeSession).run([case]))

    assert FakeFixedExecutor.initialized
    assert collector.results[0].passed
    assert list(tmp_path.glob("*.html"))
