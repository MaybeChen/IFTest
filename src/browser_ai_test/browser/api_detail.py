from __future__ import annotations

import json
import logging
from typing import Any

from browser_ai_test.config import ApiDetailConfig

logger = logging.getLogger(__name__)


class ApiDetailError(RuntimeError):
    """The host page did not return method details over postMessage."""


async def fetch_api_details(
    page: Any,
    iframe_selector: str,
    config: ApiDetailConfig,
) -> Any:
    """Request all method details from the host and return the response data.

    The request is sent from inside the iframe to ``window.parent``.  The
    response listener is installed first inside that same iframe, so this also
    works when the iframe is cross-origin.
    """
    frame = page.frame_locator(iframe_selector)
    try:
        result = await frame.locator("html").evaluate(
            """
            (element, options) => new Promise((resolve, reject) => {
              const timeoutId = window.setTimeout(() => {
                window.removeEventListener('message', onMessage);
                reject(new Error(
                  `等待 postMessage 响应超时: event=${options.responseEvent}`
                ));
              }, options.timeoutMs);

              function onMessage(messageEvent) {
                const payload = messageEvent.data;
                if (!payload || payload.event !== options.responseEvent) return;
                window.clearTimeout(timeoutId);
                window.removeEventListener('message', onMessage);
                resolve({
                  event: payload.event,
                  data: payload.data,
                  origin: messageEvent.origin,
                });
              }

              window.addEventListener('message', onMessage);
              window.parent.postMessage(
                {event: options.requestEvent, data: options.requestData},
                options.targetOrigin
              );
            })
            """,
            {
                "requestEvent": config.request_event,
                "responseEvent": config.response_event,
                "requestData": config.request_data,
                "targetOrigin": config.target_origin,
                "timeoutMs": config.timeout_ms,
            },
        )
    except Exception as exc:
        raise ApiDetailError(
            f"获取方法详情失败，iframe={iframe_selector!r}, "
            f"event={config.response_event!r}: {exc}"
        ) from exc

    logger.info(
        "API details received: event=%s origin=%s data=%s",
        result.get("event"),
        result.get("origin"),
        json.dumps(result.get("data"), ensure_ascii=False, default=str),
    )
    return result.get("data")
