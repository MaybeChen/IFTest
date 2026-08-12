from __future__ import annotations

import asyncio
import logging
from typing import Any

from browser_ai_test.models import Protocol, StreamResult

logger = logging.getLogger(__name__)


class StreamMonitorError(RuntimeError):
    """Base monitor failure."""


class StreamTimeoutError(StreamMonitorError):
    """No business completion event arrived before the configured deadline."""


class StreamMonitor:
    """Case-scoped state machine fed by monotonic CDP Network timestamps."""

    def __init__(
        self,
        url_keywords: list[str],
        done_markers: list[str],
        *,
        aborted_sse_is_complete: bool = False,
    ) -> None:
        self.url_keywords = tuple(url_keywords)
        self.done_markers = tuple(done_markers)
        self.aborted_sse_is_complete = aborted_sse_is_complete
        self.done_event = asyncio.Event()
        self.reset()

    def reset(self) -> None:
        self.done_event.clear()
        self.armed = False
        self.target_protocol: Protocol = "auto"
        self.detected_protocol: Protocol | None = None
        self.request_ids: set[str] = set()
        self.request_start_ts: float | None = None
        self.first_message_ts: float | None = None
        self.done_ts: float | None = None
        self.network_error: str | None = None

    def arm(self, protocol: Protocol = "auto") -> str:
        self.reset()
        self.target_protocol = protocol
        self.armed = True
        return "网络监听已经准备完成，现在可以点击发送。"

    def _url_matches(self, url: str) -> bool:
        return any(keyword in url for keyword in self.url_keywords)

    def _accepts(self, protocol: Protocol) -> bool:
        return self.target_protocol in ("auto", protocol)

    def _track(self, request_id: str, timestamp: float, protocol: Protocol | None = None) -> None:
        self.request_ids.add(request_id)
        if self.request_start_ts is None:
            self.request_start_ts = timestamp
        if protocol and self.detected_protocol is None:
            self.detected_protocol = protocol

    def _payload(
        self,
        request_id: str,
        timestamp: float,
        data: str,
        protocol: Protocol,
        event_name: str = "",
    ) -> None:
        if not self.armed or request_id not in self.request_ids or not self._accepts(protocol):
            return
        self.detected_protocol = protocol
        if self.first_message_ts is None:
            self.first_message_ts = timestamp
        # CDP exposes SSE's `event:` and `data:` as separate fields.  Include
        # both in matching so an empty-data terminal event (for example
        # `event:onComplete`) can be used as an exact business completion signal.
        payload = f"event:{event_name}\ndata:{data}" if event_name else data
        if any(marker in payload for marker in self.done_markers):
            self.done_ts = timestamp
            self.done_event.set()

    def on_request_will_be_sent(self, event: dict[str, Any]) -> None:
        if not self.armed:
            return
        request = event.get("request", {})
        if not self._url_matches(str(request.get("url", ""))):
            return
        resource_type = str(event.get("type", ""))
        protocol: Protocol | None = "sse" if resource_type == "EventSource" else None
        self._track(str(event["requestId"]), float(event["timestamp"]), protocol)

    def on_response_received(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId", ""))
        if request_id not in self.request_ids:
            return
        mime = str(event.get("response", {}).get("mimeType", "")).lower()
        if "event-stream" in mime:
            self.detected_protocol = "sse"
        elif self.detected_protocol is None and self._accepts("http"):
            self.detected_protocol = "http"

    def on_event_source_message_received(self, event: dict[str, Any]) -> None:
        self._payload(
            str(event.get("requestId", "")),
            float(event.get("timestamp", 0)),
            str(event.get("data", "")),
            "sse",
            str(event.get("eventName", "")),
        )

    def on_websocket_created(self, event: dict[str, Any]) -> None:
        if self.armed and self._accepts("websocket") and self._url_matches(str(event.get("url", ""))):
            # CDP creation events do not expose timestamp; requestWillBeSent usually does.
            timestamp = float(event.get("timestamp", 0))
            self._track(str(event["requestId"]), timestamp, "websocket")

    def on_websocket_frame_received(self, event: dict[str, Any]) -> None:
        self._payload(str(event.get("requestId", "")), float(event.get("timestamp", 0)), str(event.get("response", {}).get("payloadData", "")), "websocket")

    def on_websocket_closed(self, event: dict[str, Any]) -> None:
        # A shared socket may remain open; only a configured business marker completes it.
        return

    def on_loading_finished(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId", ""))
        if not self.armed or request_id not in self.request_ids or not self._accepts("http"):
            return
        if self.target_protocol == "auto" and self.detected_protocol in ("sse", "websocket"):
            return
        self.detected_protocol = "http"
        self.done_ts = float(event["timestamp"])
        self.done_event.set()

    def on_loading_failed(self, event: dict[str, Any]) -> None:
        if (
            self.armed
            and not self.done_event.is_set()
            and str(event.get("requestId", "")) in self.request_ids
        ):
            error_text = str(event.get("errorText", "Network.loadingFailed"))
            if (
                self.aborted_sse_is_complete
                and error_text == "net::ERR_ABORTED"
                and self.detected_protocol == "sse"
            ):
                # The application consumed SSE data and then intentionally
                # cancelled the fetch transport.  For this explicitly enabled
                # compatibility mode, transport abort is the terminal signal.
                self.done_ts = float(event.get("timestamp", self.request_start_ts or 0))
                self.done_event.set()
                logger.info(
                    "Treating net::ERR_ABORTED as completed SSE request: %s",
                    event.get("requestId", ""),
                )
                return
            self.network_error = error_text
            self.done_event.set()

    async def wait_done(self, timeout_seconds: float) -> StreamResult:
        try:
            await asyncio.wait_for(self.done_event.wait(), timeout_seconds)
        except TimeoutError as exc:
            self.armed = False
            kind = "未检测到目标网络请求" if not self.request_ids else "未收到业务完成信号"
            raise StreamTimeoutError(f"{timeout_seconds:g} seconds 内{kind}") from exc
        self.armed = False
        if self.network_error:
            raise StreamMonitorError(self.network_error)
        if self.request_start_ts is None or self.done_ts is None:
            raise StreamMonitorError("网络事件缺少 monotonic timestamp")
        ttft = None if self.first_message_ts is None else (self.first_message_ts - self.request_start_ts) * 1000
        return StreamResult(
            completed=True,
            protocol=self.detected_protocol,
            ttft_ms=ttft,
            stream_total_ms=(self.done_ts - self.request_start_ts) * 1000,
        )

    async def attach(self, cdp_session: Any) -> None:
        handlers = {
            "Network.requestWillBeSent": self.on_request_will_be_sent,
            "Network.responseReceived": self.on_response_received,
            "Network.loadingFinished": self.on_loading_finished,
            "Network.loadingFailed": self.on_loading_failed,
            "Network.eventSourceMessageReceived": self.on_event_source_message_received,
            "Network.webSocketCreated": self.on_websocket_created,
            "Network.webSocketFrameReceived": self.on_websocket_frame_received,
            "Network.webSocketClosed": self.on_websocket_closed,
        }
        for event, callback in handlers.items():
            cdp_session.on(event, callback)
        await cdp_session.send("Network.enable")
