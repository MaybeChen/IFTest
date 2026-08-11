import asyncio
from types import SimpleNamespace

from browser_ai_test.config import AppConfig
from browser_ai_test.models import AgentExecutionResult, AgentRun, ExpectedConfig, TestCase as CaseModel
from browser_ai_test.runner import TestRunner as Runner


class FakeDatabase:
    def start_run(self, *args): pass
    def save_case(self, result): self.result = result
    def finish_run(self, *args): pass


class FakeSession:
    seen_enable_browser_use = None

    def __init__(self, browser, stream, enable_browser_use=True):
        type(self).seen_enable_browser_use = enable_browser_use
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
        return AgentRun(AgentExecutionResult(answer="标准答案", page_ok=True, reason="ok"), 4, 1.0)


def test_playwright_mode_never_creates_llm_or_browser_use(monkeypatch, tmp_path):
    import browser_ai_test.runner as runner_module

    config = AppConfig.model_validate({
        "browser": {}, "system": {"url": "https://test", "iframe_selector": "#frame"},
        "stream": {"url_keywords": ["/stream"], "done_markers": ["[DONE]"]},
        "execution": {"mode": "playwright"}, "runner": {"case_interval_seconds": 0},
        "report": {"html_directory": str(tmp_path)},
    })
    case = CaseModel(id="C1", name="case", question="q", expected=ExpectedConfig(type="keyword", values=["答案"]))
    monkeypatch.setattr(runner_module, "create_llm", lambda config: (_ for _ in ()).throw(AssertionError("LLM must not be created")))
    monkeypatch.setattr(runner_module, "FixedPlaywrightExecutor", FakeFixedExecutor)
    monkeypatch.setattr(runner_module, "render_case", lambda *args: None)
    monkeypatch.setattr(runner_module, "render_summary", lambda *args: None)

    _, collector = asyncio.run(Runner(config, FakeDatabase(), FakeSession).run([case]))

    assert FakeSession.seen_enable_browser_use is False
    assert FakeFixedExecutor.initialized
    assert collector.results[0].passed
    assert list(tmp_path.glob("*.html"))
