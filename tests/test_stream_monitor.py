import asyncio

import pytest

from browser_ai_test.browser.stream_monitor import StreamMonitor, StreamTimeoutError


def monitor(protocol="auto"):
    item = StreamMonitor(["/api/stream"], ["[DONE]", '"status":"completed"'])
    item.arm(protocol)
    return item


def request(item, request_id="1", url="https://test/api/stream", ts=10.0, kind="Fetch"):
    item.on_request_will_be_sent({"requestId": request_id, "timestamp": ts, "type": kind, "request": {"url": url}})


def test_url_filter_and_done_marker():
    item = monitor("sse")
    request(item, url="https://test/unrelated")
    item.on_event_source_message_received({"requestId": "1", "timestamp": 11, "data": "[DONE]"})
    assert not item.done_event.is_set()
    assert not item.request_ids


def test_sse_completed():
    item = monitor("sse"); request(item, kind="EventSource")
    item.on_event_source_message_received({"requestId": "1", "timestamp": 10.5, "data": "token"})
    item.on_event_source_message_received({"requestId": "1", "timestamp": 12, "data": "[DONE]"})
    result = asyncio.run(item.wait_done(0.1))
    assert result.protocol == "sse"
    assert result.ttft_ms == pytest.approx(500)
    assert result.stream_total_ms == pytest.approx(2000)


def test_websocket_completed_without_close():
    item = monitor("websocket")
    item.on_websocket_created({"requestId": "ws", "url": "wss://test/api/stream", "timestamp": 20})
    item.on_websocket_frame_received({"requestId": "ws", "timestamp": 20.25, "response": {"payloadData": "token"}})
    item.on_websocket_frame_received({"requestId": "ws", "timestamp": 21, "response": {"payloadData": '{"status":"completed"}'}})
    result = asyncio.run(item.wait_done(0.1))
    assert result.protocol == "websocket"
    assert result.stream_total_ms == pytest.approx(1000)


def test_http_completed():
    item = monitor("http"); request(item)
    item.on_loading_finished({"requestId": "1", "timestamp": 13})
    result = asyncio.run(item.wait_done(0.1))
    assert result.protocol == "http"
    assert result.ttft_ms is None
    assert result.stream_total_ms == pytest.approx(3000)


def test_timeout_is_explicit_and_reset_isolation():
    item = monitor("sse"); request(item)
    with pytest.raises(StreamTimeoutError, match="未收到业务完成信号"):
        asyncio.run(item.wait_done(0.001))
    item.arm("http")
    assert not item.request_ids and not item.done_event.is_set()
