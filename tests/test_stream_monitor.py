import asyncio
import logging

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


def test_unmatched_eventsource_logs_real_url_and_keywords(caplog):
    item = StreamMonitor(["/expected/chat"], ["event:onComplete"])
    item.arm("sse")

    with caplog.at_level(logging.WARNING):
        request(item, url="https://test/actual/chat/events", kind="EventSource")

    assert "actual/chat/events" in caplog.text
    assert "/expected/chat" in caplog.text
    assert not item.request_ids


def test_unmatched_fetch_sse_response_logs_real_url(caplog):
    item = StreamMonitor(["/expected/chat"], ["event:onComplete"])
    item.arm("sse")
    request(item, url="https://test/actual/chat/events", kind="Fetch")

    with caplog.at_level(logging.WARNING):
        item.on_response_received(
            {"requestId": "1", "response": {"mimeType": "text/event-stream"}}
        )

    assert "actual/chat/events" in caplog.text
    assert "SSE response ignored" in caplog.text


def test_sse_completed():
    item = monitor("sse"); request(item, kind="EventSource")
    item.on_event_source_message_received({"requestId": "1", "timestamp": 10.5, "data": "token"})
    item.on_event_source_message_received({"requestId": "1", "timestamp": 12, "data": "[DONE]"})
    result = asyncio.run(item.wait_done(0.1))
    assert result.protocol == "sse"
    assert result.ttft_ms == pytest.approx(500)
    assert result.stream_total_ms == pytest.approx(2000)


def test_sse_empty_data_on_complete_event_finishes_stream():
    item = StreamMonitor(["/api/stream"], ["event:onComplete"])
    item.arm("sse")
    request(item, kind="EventSource")
    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 10.5, "eventName": "onResult", "data": '{"state":"success","done":false}'}
    )
    assert not item.done_event.is_set()

    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 12, "eventName": "onComplete", "data": ""}
    )

    result = asyncio.run(item.wait_done(0.1))
    assert result.protocol == "sse"
    assert result.stream_total_ms == pytest.approx(2000)


def test_sse_done_event_name_is_matched_exactly_with_empty_data():
    item = StreamMonitor(
        ["/api/stream"], ["unused-marker"], done_event_names=["onComplete"]
    )
    item.arm("sse")
    request(item, kind="EventSource")
    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 11, "eventName": "onPlan", "data": ""}
    )
    assert not item.done_event.is_set()

    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 12, "eventName": "onComplete", "data": ""}
    )
    result = asyncio.run(item.wait_done(0.1))

    assert result.completed
    assert result.protocol == "sse"


def test_loading_failed_after_business_complete_is_ignored():
    item = StreamMonitor(["/api/stream"], ["event:onComplete"])
    item.arm("sse")
    request(item, kind="EventSource")
    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 12, "eventName": "onComplete", "data": ""}
    )
    item.on_loading_failed({"requestId": "1", "errorText": "net::ERR_ABORTED"})

    result = asyncio.run(item.wait_done(0.1))
    assert result.completed
    assert item.network_error is None


def test_configured_sse_abort_after_data_is_completion():
    item = StreamMonitor(
        ["/api/stream"], ["event:onComplete"], aborted_sse_is_complete=True
    )
    item.arm("sse")
    request(item, kind="EventSource")
    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 11, "eventName": "onResult", "data": "answer"}
    )
    item.on_loading_failed(
        {"requestId": "1", "timestamp": 12, "errorText": "net::ERR_ABORTED"}
    )

    result = asyncio.run(item.wait_done(0.1))
    assert result.completed
    assert result.stream_total_ms == pytest.approx(2000)
    assert item.network_error is None


def test_configured_fetch_sse_abort_completes_without_eventsource_messages():
    item = StreamMonitor(
        ["/api/stream"], ["event:onComplete"], aborted_sse_is_complete=True
    )
    item.arm("sse")
    request(item, kind="Fetch")
    item.on_response_received(
        {"requestId": "1", "response": {"mimeType": "text/event-stream"}}
    )
    item.on_loading_failed(
        {"requestId": "1", "timestamp": 12, "errorText": "net::ERR_ABORTED"}
    )

    result = asyncio.run(item.wait_done(0.1))
    assert result.completed
    assert result.ttft_ms is None
    assert result.stream_total_ms == pytest.approx(2000)


def test_configured_fetch_sse_loading_finished_completes_stream():
    item = StreamMonitor(
        ["/api/stream"],
        ["event:onComplete"],
        sse_loading_finished_is_complete=True,
    )
    item.arm("sse")
    request(item, kind="Fetch")
    item.on_response_received(
        {"requestId": "1", "response": {"mimeType": "text/event-stream"}}
    )
    item.on_loading_finished({"requestId": "1", "timestamp": 15})

    result = asyncio.run(item.wait_done(0.1))
    assert result.completed
    assert result.protocol == "sse"
    assert result.stream_total_ms == pytest.approx(5000)


def test_sse_loading_finished_does_not_complete_without_opt_in():
    item = StreamMonitor(["/api/stream"], ["event:onComplete"])
    item.arm("sse")
    request(item, kind="Fetch")
    item.on_response_received(
        {"requestId": "1", "response": {"mimeType": "text/event-stream"}}
    )
    item.on_loading_finished({"requestId": "1", "timestamp": 15})

    assert not item.done_event.is_set()


def test_sse_abort_is_error_without_explicit_compatibility_mode():
    item = StreamMonitor(["/api/stream"], ["event:onComplete"])
    item.arm("sse")
    request(item, kind="EventSource")
    item.on_event_source_message_received(
        {"requestId": "1", "timestamp": 11, "eventName": "onResult", "data": "answer"}
    )
    item.on_loading_failed(
        {"requestId": "1", "timestamp": 12, "errorText": "net::ERR_ABORTED"}
    )

    with pytest.raises(Exception, match="net::ERR_ABORTED"):
        asyncio.run(item.wait_done(0.1))


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
