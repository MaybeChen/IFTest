from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener

logger = logging.getLogger(__name__)


class DetachableCDPSession(Protocol):
    async def detach(self) -> None: ...


class CDPConnectionError(ConnectionError):
    """The external Chrome debugging endpoint is unavailable or invalid."""


def frame_uses_parent_cdp_session(error: BaseException) -> bool:
    """Return whether Playwright says an iframe shares its parent's target."""
    return "part of the parent frame's session" in str(error)


async def detach_cdp_session_safely(
    session: DetachableCDPSession | None, *, label: str
) -> None:
    """Best-effort detach; navigation may already have destroyed the target."""
    if session is None:
        return
    try:
        await session.detach()
    except Exception as exc:
        message = str(exc)
        if "Target page, context or browser has been closed" in message or "Target closed" in message:
            logger.info("CDP session already closed; detach skipped: %s", label)
            return
        raise


def ensure_loopback_no_proxy(cdp_url: str) -> None:
    """Prevent HTTP clients from proxying local CDP traffic."""
    hostname = urlparse(cdp_url).hostname
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        return
    required = ("localhost", "127.0.0.1", "::1")
    for variable in ("NO_PROXY", "no_proxy"):
        current = [item.strip() for item in os.getenv(variable, "").split(",") if item.strip()]
        lowered = {item.lower() for item in current}
        current.extend(item for item in required if item.lower() not in lowered)
        os.environ[variable] = ",".join(current)


def fetch_cdp_version(cdp_url: str, timeout_seconds: float) -> dict[str, Any]:
    version_url = f"{cdp_url.rstrip('/')}/json/version"
    # An empty ProxyHandler deliberately bypasses system/corporate proxies for preflight.
    try:
        with build_opener(ProxyHandler({})).open(version_url, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CDPConnectionError(
            f"无法直连 Chrome CDP {version_url}: {exc}. 请确认 Chrome 已启动、端口正确，"
            "并将 localhost/127.0.0.1 加入 NO_PROXY。"
        ) from exc
    if status != 200:
        raise CDPConnectionError(f"Chrome CDP {version_url} 返回 HTTP {status}")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CDPConnectionError(
            f"Chrome CDP {version_url} 未返回 JSON；可能被 HTTP 代理或网关拦截"
        ) from exc
    if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
        raise CDPConnectionError(f"Chrome CDP {version_url} 响应缺少 webSocketDebuggerUrl")
    return payload
