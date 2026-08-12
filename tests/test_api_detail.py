import asyncio

import pytest

from browser_ai_test.browser.api_detail import (
    ApiDetailError,
    fetch_api_details,
    find_page_with_iframe,
)
from browser_ai_test.config import ApiDetailConfig


class FakeHtmlLocator:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.expression = None
        self.options = None

    async def evaluate(self, expression, options):
        self.expression = expression
        self.options = options
        if self.error:
            raise self.error
        return self.result


class FakeFrame:
    def __init__(self, locator): self.html = locator
    def locator(self, selector):
        assert selector == "html"
        return self.html


class FakePage:
    def __init__(self, locator): self.html = locator; self.selector = None
    def frame_locator(self, selector):
        self.selector = selector
        return FakeFrame(self.html)


class SearchLocator:
    def __init__(self, count): self.value = count
    async def count(self): return self.value


class SearchPage:
    def __init__(self, url, count): self.url = url; self.value = count
    def locator(self, selector): return SearchLocator(self.value)


def test_fetch_api_details_posts_request_and_returns_response_data():
    locator = FakeHtmlLocator(
        result={
            "event": "getApiDetail",
            "data": [{"name": "method-a", "path": "/a"}],
            "origin": "https://host.test",
        }
    )
    page = FakePage(locator)
    config = ApiDetailConfig(timeout_ms=4321)

    details = asyncio.run(fetch_api_details(page, "#methodCopilot", config))

    assert details == [{"name": "method-a", "path": "/a"}]
    assert page.selector == "#methodCopilot"
    assert locator.options == {
        "requestEvent": "getApiDetail",
        "responseEvent": "getApiDetail",
        "requestData": {},
        "targetOrigin": "*",
        "timeoutMs": 4321.0,
    }
    assert "addEventListener('message'" in locator.expression
    assert locator.expression.index("addEventListener('message'") < locator.expression.index("window.parent.postMessage")


def test_fetch_api_details_reports_postmessage_timeout():
    page = FakePage(FakeHtmlLocator(error=RuntimeError("等待 postMessage 响应超时")))

    with pytest.raises(ApiDetailError, match="getApiDetail"):
        asyncio.run(fetch_api_details(page, "#methodCopilot", ApiDetailConfig()))


def test_find_page_with_iframe_prefers_most_recent_matching_page():
    pages = [SearchPage("https://old", 1), SearchPage("https://current", 1)]

    selected = asyncio.run(find_page_with_iframe(pages, "#methodCopilot"))

    assert selected.url == "https://current"


def test_find_page_with_iframe_requires_manually_prepared_page():
    with pytest.raises(ApiDetailError, match="请先手动打开目标界面"):
        asyncio.run(find_page_with_iframe([SearchPage("https://other", 0)], "#methodCopilot"))
