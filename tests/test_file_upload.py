import asyncio

import pytest

from browser_ai_test.browser.file_upload import FileUploadError, resolve_case_file, upload_case_file
from browser_ai_test.config import UploadConfig


class FakeLocator:
    def __init__(self, counts, calls, name):
        self.counts = counts
        self.calls = calls
        self.name = name

    async def count(self):
        return self.counts.get(self.name, 0)

    @property
    def first(self):
        return self

    async def set_input_files(self, path, **kwargs):
        self.calls.append((self.name, path, kwargs))

    async def click(self, **kwargs):
        self.calls.append((self.name, "click", kwargs))


class FakeChooser:
    def __init__(self, calls): self.calls = calls
    async def set_files(self, path): self.calls.append(("chooser", "set_files", path))


class FakeChooserInfo:
    def __init__(self, calls): self.value = self._value(calls)
    async def _value(self, calls): return FakeChooser(calls)
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class FakeFrame:
    def __init__(self, counts, calls, prefix):
        self.counts = counts; self.calls = calls; self.prefix = prefix

    def locator(self, selector):
        return FakeLocator(self.counts, self.calls, f"{self.prefix}:{selector}")


class FakePage(FakeFrame):
    def __init__(self, counts, calls):
        super().__init__(counts, calls, "main")
        self.frames = [FakeFrame(counts, calls, "semantic-frame")]

    def frame_locator(self, selector):
        return FakeFrame(self.counts, self.calls, f"frame({selector})")

    def expect_file_chooser(self, **kwargs):
        self.calls.append(("expect_file_chooser", kwargs))
        return FakeChooserInfo(self.calls)


def test_resolve_case_file_rejects_missing_and_traversal(tmp_path):
    with pytest.raises(FileUploadError, match="不存在"):
        resolve_case_file(tmp_path, "missing.pdf")
    outside = tmp_path.parent / "secret.pdf"
    outside.write_text("secret")
    with pytest.raises(FileUploadError, match="越过"):
        resolve_case_file(tmp_path, "../secret.pdf")


def test_uploads_exact_file_to_configured_iframe(tmp_path):
    attachment = tmp_path / "manual.pdf"
    attachment.write_bytes(b"pdf")
    calls = []
    selector = "input[type='file']"
    counts = {f"frame(#business):{selector}": 1}
    config = UploadConfig(directory=tmp_path, target="iframe", timeout_ms=4321)

    uploaded = asyncio.run(upload_case_file(FakePage(counts, calls), "manual.pdf", config, "#business"))

    assert uploaded == attachment.resolve()
    assert calls == [(f"frame(#business):{selector}", str(attachment.resolve()), {"timeout": 4321.0})]


def test_auto_discovers_file_input_in_semantic_frame(tmp_path):
    attachment = tmp_path / "data.csv"
    attachment.write_text("a,b")
    calls = []
    selector = "#upload"
    counts = {f"semantic-frame:{selector}": 1}
    config = UploadConfig(directory=tmp_path, input_selector=selector, target="auto")

    asyncio.run(upload_case_file(FakePage(counts, calls), "data.csv", config, None))

    assert calls[0][0] == "semantic-frame:#upload"


def test_explicit_iframe_target_requires_selector(tmp_path):
    attachment = tmp_path / "data.txt"
    attachment.write_text("data")
    with pytest.raises(FileUploadError, match="iframe_selector"):
        asyncio.run(upload_case_file(FakePage({}, []), "data.txt", UploadConfig(directory=tmp_path, target="iframe"), None))


def test_trigger_upload_handles_file_chooser_without_leaving_dialog_open(tmp_path):
    attachment = tmp_path / "manual.docx"
    attachment.write_bytes(b"docx")
    calls = []
    config = UploadConfig(
        directory=tmp_path, target="iframe", trigger_selector=".chat-input-icon",
        timeout_ms=5000,
    )
    asyncio.run(
        upload_case_file(FakePage({}, calls), "manual.docx", config, "#methodCopilot")
    )
    assert calls[0] == ("expect_file_chooser", {"timeout": 5000.0})
    assert calls[1][0:2] == ("frame(#methodCopilot):.chat-input-icon", "click")
    assert calls[2] == ("chooser", "set_files", str(attachment.resolve()))
