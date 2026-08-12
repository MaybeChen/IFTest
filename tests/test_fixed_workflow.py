import asyncio

import pytest

from browser_ai_test.browser.fixed_workflow import FixedPlaywrightExecutor
from browser_ai_test.config import LoginConfig, SystemConfig, UploadConfig, WorkflowConfig
from browser_ai_test.models import ExpectedConfig, TestCase as CaseModel


class FakeLocator:
    def __init__(self, selector, calls, visible=True):
        self.selector = selector; self.calls = calls; self.visible = visible

    async def is_visible(self, **kwargs):
        self.calls.append(("visible", self.selector, kwargs)); return self.visible

    async def fill(self, value, **kwargs):
        self.calls.append(("fill", self.selector, value, kwargs))

    async def click(self, **kwargs):
        self.calls.append(("click", self.selector, kwargs))

    async def inner_text(self, **kwargs):
        self.calls.append(("inner_text", self.selector, kwargs)); return "页面生成的标准答案"

    async def wait_for(self, **kwargs):
        self.calls.append(("wait_for", self.selector, kwargs))

    async def element_handle(self, **kwargs):
        self.calls.append(("element_handle", self.selector, kwargs))
        return FakeElementHandle(self.calls, self.selector)

    def nth(self, index):
        return FakeLocator(f"{self.selector}:nth({index})", self.calls, self.visible)


class FakeRoot:
    def __init__(self, calls, prefix): self.calls = calls; self.prefix = prefix
    def locator(self, selector): return FakeLocator(f"{self.prefix}:{selector}", self.calls)


class FakeFrame:
    def __init__(self, calls, selector): self.calls = calls; self.selector = selector
    async def reload(self, **kwargs): self.calls.append(("frame_reload", self.selector, kwargs))


class FakeElementHandle:
    def __init__(self, calls, selector): self.calls = calls; self.selector = selector
    async def content_frame(self): return FakeFrame(self.calls, self.selector)


class FakePage(FakeRoot):
    def __init__(self): super().__init__([], "main"); self.frames = []
    def frame_locator(self, selector): return FakeRoot(self.calls, f"frame({selector})")
    async def goto(self, url, **kwargs): self.calls.append(("goto", url, kwargs))
    async def reload(self, **kwargs): self.calls.append(("reload", kwargs))


class FakeMonitor:
    def __init__(self): self.target_protocol = "sse"; self.calls = []
    def arm(self, protocol): self.target_protocol = protocol; self.calls.append(("arm", protocol))
    async def wait_done(self, timeout): self.calls.append(("wait", timeout))


def test_fixed_workflow_logs_in_runs_case_and_refreshes(monkeypatch):
    monkeypatch.setenv("QA_USER", "tester")
    monkeypatch.setenv("QA_PASSWORD", "secret")
    page = FakePage(); monitor = FakeMonitor()
    workflow = WorkflowConfig(
        login=LoginConfig(enabled=True, username_env="QA_USER", password_env="QA_PASSWORD"),
        question_selector="#question", send_selector="#send", answer_selector="#answer",
        target="iframe", refresh_action="reload", step_interval_seconds=0,
        case_ready_selector="#question",
        after_refresh_steps=[],
    )
    executor = FixedPlaywrightExecutor(
        page, monitor, SystemConfig(url="https://test", iframe_selector="#frame"),
        UploadConfig(), workflow, 120,
    )
    case = CaseModel(
        id="1", name="qa", question="问题", expected=ExpectedConfig(type="keyword", values=["答案"])
    )

    asyncio.run(executor.initialize())
    result = asyncio.run(executor.execute(case))

    assert result.result.answer == "页面生成的标准答案"
    assert result.result.page_ok
    assert ("arm", "sse") in monitor.calls and ("wait", 120) in monitor.calls
    assert any(call[:3] == ("fill", "main:input[placeholder='w3账号']", "tester") for call in page.calls)
    assert any(call[:3] == ("fill", "main:input[type='password']", "secret") for call in page.calls)
    assert any(call[:3] == ("fill", "frame(#frame):#question", "问题") for call in page.calls)
    assert any(call[0] == "reload" for call in page.calls)
    ready = [call for call in page.calls if call[0:2] == ("wait_for", "frame(#frame):#question")]
    assert len(ready) == 2


def test_fixed_workflow_does_not_require_login_when_hidden(monkeypatch):
    page = FakePage()
    original = page.locator
    page.locator = lambda selector: FakeLocator(f"main:{selector}", page.calls, visible=False)
    executor = FixedPlaywrightExecutor(
        page, FakeMonitor(), SystemConfig(url="https://test", iframe_selector="#frame"),
        UploadConfig(), WorkflowConfig(login=LoginConfig(enabled=True), step_interval_seconds=0), 30,
    )
    asyncio.run(executor.initialize())
    assert not any(call[0] == "fill" for call in page.calls)


def test_iframe_reload_preserves_outer_page_and_prepares_next_case():
    page = FakePage()
    workflow = WorkflowConfig(
        question_selector="#question", send_selector="#send", answer_selector="#answer",
        target="iframe", refresh_action="iframe_reload", case_ready_selector="#question",
        step_interval_seconds=0,
    )
    executor = FixedPlaywrightExecutor(
        page, FakeMonitor(), SystemConfig(url="https://test", iframe_selector="#frame"),
        UploadConfig(), workflow, 30,
    )
    case = CaseModel(
        id="1", name="qa", question="问题",
        expected=ExpectedConfig(type="keyword", values=["答案"]),
    )

    asyncio.run(executor.execute(case))

    assert not any(call[0] == "reload" for call in page.calls)
    assert any(call[0:2] == ("frame_reload", "main:#frame") for call in page.calls)
    assert page.calls[-1][0:2] == ("wait_for", "frame(#frame):#question")


def test_fixed_workflow_runs_upload_focus_steps_and_question_nth(monkeypatch):
    from browser_ai_test.models import PlaywrightStep

    async def fake_upload(*args):
        page.calls.append(("upload", args[1]))

    monkeypatch.setattr(
        "browser_ai_test.browser.fixed_workflow.upload_case_file", fake_upload
    )

    page = FakePage(); monitor = FakeMonitor()
    workflow = WorkflowConfig(
        before_case_steps=[PlaywrightStep(action="click", selector=".chat-input-icon")],
        after_upload_steps=[
            PlaywrightStep(action="click", selector=".cb-chatbot-content"),
            PlaywrightStep(action="click", selector=".wise-input"),
        ],
        question_selector="span", question_nth=3,
        send_selector=".send", answer_selector=".answer", target="iframe",
        refresh_action="none", step_interval_seconds=0,
    )
    executor = FixedPlaywrightExecutor(
        page, monitor, SystemConfig(url="https://test", iframe_selector="#methodCopilot"),
        UploadConfig(), workflow, 30,
    )
    case = CaseModel(
        id="1", name="qa", file="manual.docx", question="根据文档生成接口",
        expected=ExpectedConfig(type="keyword", values=["接口"]),
    )
    result = asyncio.run(executor.execute(case))
    assert result.steps == 7
    assert any(call[0:2] == ("click", "frame(#methodCopilot):.chat-input-icon") for call in page.calls)
    upload_index = page.calls.index(("upload", "manual.docx"))
    content_index = next(i for i, call in enumerate(page.calls) if call[0:2] == ("click", "frame(#methodCopilot):.cb-chatbot-content"))
    input_index = next(i for i, call in enumerate(page.calls) if call[0:2] == ("click", "frame(#methodCopilot):.wise-input"))
    fill_index = next(i for i, call in enumerate(page.calls) if call[:3] == ("fill", "frame(#methodCopilot):span:nth(3)", "根据文档生成接口"))
    assert upload_index < content_index < input_index < fill_index


def test_failed_case_refreshes_and_restores_ui_for_next_case():
    class FailingMonitor(FakeMonitor):
        async def wait_done(self, timeout):
            raise RuntimeError("stream failed")

    page = FakePage()
    from browser_ai_test.models import PlaywrightStep
    workflow = WorkflowConfig(
        question_selector="#question", send_selector="#send", target="iframe",
        refresh_action="reload", case_ready_selector="#question",
        after_refresh_steps=[
            PlaywrightStep(action="click", target="main", selector=".ai-toggle-btn")
        ],
        step_interval_seconds=0,
    )
    executor = FixedPlaywrightExecutor(
        page, FailingMonitor(),
        SystemConfig(url="https://test", iframe_selector="#frame"),
        UploadConfig(), workflow, 30,
    )
    case = CaseModel(
        id="failed", name="qa", question="问题",
        expected=ExpectedConfig(type="keyword", values=["答案"]),
    )

    with pytest.raises(RuntimeError, match="stream failed"):
        asyncio.run(executor.execute(case))

    assert any(call[0] == "reload" for call in page.calls)
    assert any(call[0:2] == ("click", "main:.ai-toggle-btn") for call in page.calls)
    assert page.calls[-1][0:2] == ("wait_for", "frame(#frame):#question")
