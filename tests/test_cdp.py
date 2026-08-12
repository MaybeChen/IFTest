import pytest
import asyncio

from browser_ai_test.browser import cdp


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, url, timeout):
        self.calls.append((url, timeout))
        return self.response


def test_loopback_hosts_are_added_to_both_no_proxy_variables(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "internal.example")
    monkeypatch.delenv("no_proxy", raising=False)

    cdp.ensure_loopback_no_proxy("http://localhost:9222")

    for variable in ("NO_PROXY", "no_proxy"):
        values = set(cdp.os.environ[variable].split(","))
        assert {"localhost", "127.0.0.1", "::1"} <= values
    assert "internal.example" in cdp.os.environ["NO_PROXY"]


def test_remote_cdp_does_not_change_proxy_environment(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "existing")
    monkeypatch.setenv("no_proxy", "existing")
    cdp.ensure_loopback_no_proxy("http://chrome.internal:9222")
    assert cdp.os.environ["NO_PROXY"] == "existing"
    assert cdp.os.environ["no_proxy"] == "existing"


def test_preflight_bypasses_proxy_and_validates_payload(monkeypatch):
    opener = FakeOpener(FakeResponse(b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/1"}'))
    monkeypatch.setattr(cdp, "build_opener", lambda handler: opener)

    result = cdp.fetch_cdp_version("http://127.0.0.1:9222/", 3)

    assert result["webSocketDebuggerUrl"].startswith("ws://")
    assert opener.calls == [("http://127.0.0.1:9222/json/version", 3)]


def test_preflight_rejects_proxy_html(monkeypatch):
    opener = FakeOpener(FakeResponse(b"<html>Gateway Timeout</html>"))
    monkeypatch.setattr(cdp, "build_opener", lambda handler: opener)
    with pytest.raises(cdp.CDPConnectionError, match="未返回 JSON"):
        cdp.fetch_cdp_version("http://localhost:9222", 3)


def test_preflight_requires_websocket_debugger_url(monkeypatch):
    opener = FakeOpener(FakeResponse(b'{"Browser":"Chrome"}'))
    monkeypatch.setattr(cdp, "build_opener", lambda handler: opener)
    with pytest.raises(cdp.CDPConnectionError, match="webSocketDebuggerUrl"):
        cdp.fetch_cdp_version("http://localhost:9222", 3)


def test_same_process_iframe_error_is_recognized_as_parent_session():
    error = RuntimeError(
        "BrowserContext.new_cdp_session: This frame does not have a separate "
        "CDP session, it is a part of the parent frame's session"
    )

    assert cdp.frame_uses_parent_cdp_session(error)
    assert not cdp.frame_uses_parent_cdp_session(RuntimeError("Target closed"))


def test_detach_ignores_session_destroyed_by_navigation():
    class ClosedSession:
        async def detach(self):
            raise RuntimeError("Target page, context or browser has been closed")

    asyncio.run(cdp.detach_cdp_session_safely(ClosedSession(), label="iframe"))


def test_detach_does_not_hide_unexpected_errors():
    class BrokenSession:
        async def detach(self):
            raise RuntimeError("protocol failure")

    with pytest.raises(RuntimeError, match="protocol failure"):
        asyncio.run(cdp.detach_cdp_session_safely(BrokenSession(), label="iframe"))
