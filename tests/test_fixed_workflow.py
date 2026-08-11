import asyncio

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


class FakeRoot:
    def __init__(self, calls, prefix): self.calls = calls; self.prefix = prefix
    def locator(self, selector): return FakeLocator(f"{self.prefix}:{selector}", self.calls)


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
        target="iframe", refresh_action="reload",
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
    assert any(call[:3] == ("fill", "main:input[name='username']", "tester") for call in page.calls)
    assert any(call[:3] == ("fill", "frame(#frame):#question", "问题") for call in page.calls)
    assert any(call[0] == "reload" for call in page.calls)


def test_fixed_workflow_does_not_require_login_when_hidden(monkeypatch):
    page = FakePage()
    original = page.locator
    page.locator = lambda selector: FakeLocator(f"main:{selector}", page.calls, visible=False)
    executor = FixedPlaywrightExecutor(
        page, FakeMonitor(), SystemConfig(url="https://test", iframe_selector="#frame"),
        UploadConfig(), WorkflowConfig(login=LoginConfig(enabled=True)), 30,
    )
    asyncio.run(executor.initialize())
    assert not any(call[0] == "fill" for call in page.calls)
