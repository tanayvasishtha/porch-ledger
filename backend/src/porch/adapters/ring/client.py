"""Ring Partner API client on httpx2.

The bearer token is attached per request, never as a client default, so
following the snapshot 303 to a pre-signed host cannot leak it. PortError
messages carry the HTTP status and the Ring problem `code`; the token is
never part of an error message.
"""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass
from typing import Any

import httpx2
import truststore

from porch.config import Settings
from porch.ports import PortError

_SEE_OTHER = 303
_NOT_FOUND = 404
# Seen live on the Playground: 422 GRECO_NO_VALID_KEY when a frame cannot be decrypted.
# It is per-frame, so the event keeps its other media.
_NO_MEDIA = frozenset({_NOT_FOUND, 422})
_OK = 200
_PARTIAL = 206
_TOO_MANY = 429
_RETRYABLE_MEDIA = frozenset({416, 425})


@dataclass(frozen=True, slots=True)
class RingEvent:
    """One row of the Event History response."""

    id: str
    device_id: str
    event_type: str
    sub_type: str | None
    start_ms: int
    end_ms: int


class RingClient:
    def __init__(
        self,
        settings: Settings,
        token: str,
        client: httpx2.AsyncClient | None = None,
        sleep: Any = None,
    ) -> None:
        self._token = token
        self._page_limit = settings.ring.history_page_limit
        self._retry_schedule = settings.ring.media_retry_schedule_s
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._client = client or httpx2.AsyncClient(
            base_url=settings.ring.base_url,
            timeout=settings.ring.request_timeout_s,
            # The OS trust store: certifi alone failed live on a pre-signed media host on Windows.
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )

    async def user(self) -> dict[str, Any]:
        response = await self._request("user", "GET", "/v1/users/me")
        _check("user", response, 200)
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def devices(self) -> list[dict[str, Any]]:
        response = await self._request("devices", "GET", "/v1/devices")
        _check("devices", response, 200)
        payload = response.json()
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return [item for item in data if isinstance(item, dict)]

    async def history(self, device_id: str, since_ms: int) -> list[RingEvent]:
        """Events with start >= since_ms; newest-first pages via links.next."""
        events: list[RingEvent] = []
        url: str | None = f"/v1/history/devices/{device_id}/events"
        for _ in range(self._page_limit):
            if url is None:
                break
            response = await self._request("history", "GET", url)
            _check("history", response, 200)
            payload = response.json()
            data = payload.get("data", []) if isinstance(payload, dict) else []
            events.extend(
                event
                for item in data
                if (event := _ring_event(item)) is not None and event.start_ms >= since_ms
            )
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            next_link = links.get("next") if isinstance(links, dict) else None
            url = next_link if isinstance(next_link, str) else None
        return sorted(events, key=lambda event: event.start_ms)

    async def snapshot(self, device_id: str, at_ms: int) -> bytes | None:
        """Two-step image download: POST -> 303 -> GET the pre-signed URL."""
        body = {
            "type": "at_timestamp",
            "timestamp": at_ms,
            "image_options": {"format": "jpeg"},
        }
        response = await self._request(
            "snapshot", "POST", f"/v1/devices/{device_id}/media/image/download", json=body
        )
        if response.status_code in _NO_MEDIA:
            return None
        if response.status_code != _SEE_OTHER:
            raise _status_error("snapshot", response)
        return await self._presigned("snapshot", response)

    async def clip(self, device_id: str, start_ms: int, duration_ms: int) -> bytes | None:
        """Video download, inline or via 303; 416/425 retried on the documented schedule."""
        body = {"timestamp": start_ms, "duration": duration_ms}
        attempts = len(self._retry_schedule) + 1
        for attempt in range(attempts):
            response = await self._request(
                "clip", "POST", f"/v1/devices/{device_id}/media/video/download", json=body
            )
            if response.status_code in (_OK, _PARTIAL):
                return response.content
            if response.status_code == _SEE_OTHER:
                return await self._presigned("clip", response)
            if response.status_code in _NO_MEDIA:
                return None
            if response.status_code not in _RETRYABLE_MEDIA:
                raise _status_error("clip", response)
            if attempt + 1 < attempts:
                await self._sleep(self._retry_schedule[attempt])
        return None

    async def _presigned(self, op: str, redirect: httpx2.Response) -> bytes | None:
        location = redirect.headers.get("location")
        if not location:
            return None
        try:
            # No auth header here: the pre-signed host must never see the token.
            media = await self._client.get(location)
        except httpx2.HTTPError as exc:
            raise _transport_error(op, exc) from exc
        if media.status_code in _NO_MEDIA:
            return None
        if media.status_code not in (_OK, _PARTIAL):
            raise _status_error(op, media)
        return media.content

    async def _request(self, op: str, method: str, url: str, **kwargs: Any) -> httpx2.Response:
        try:
            response = await self._client.request(
                method, url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs
            )
        except httpx2.HTTPError as exc:
            raise _transport_error(op, exc) from exc
        # Docs: 429 carries Retry-After; honour it once.
        if response.status_code == _TOO_MANY and "retry-after" in response.headers:
            delay = _retry_after(response)
            await self._sleep(delay)
            try:
                response = await self._client.request(
                    method, url, headers={"Authorization": f"Bearer {self._token}"}, **kwargs
                )
            except httpx2.HTTPError as exc:
                raise _transport_error(op, exc) from exc
        return response


def _ring_event(item: Any) -> RingEvent | None:
    if not isinstance(item, dict):
        return None
    attributes = item.get("attributes", {})
    if not isinstance(attributes, dict):
        return None
    source = item.get("relationships", {}).get("source", {})
    device = source.get("data", {}).get("id", "") if isinstance(source, dict) else ""
    event_type = attributes.get("event_type")
    if not isinstance(event_type, str) or not isinstance(item.get("id"), str):
        return None
    return RingEvent(
        id=item["id"],
        device_id=device,
        event_type=event_type,
        sub_type=attributes.get("sub_type"),
        start_ms=int(attributes.get("start", 0)),
        end_ms=int(attributes.get("end", 0)),
    )


def _check(op: str, response: httpx2.Response, expected: int) -> None:
    if response.status_code != expected:
        raise _status_error(op, response)


def _retry_after(response: httpx2.Response) -> float:
    try:
        return max(float(response.headers["retry-after"]), 0.0)
    except ValueError:
        return 0.0


def _transport_error(op: str, exc: httpx2.HTTPError) -> PortError:
    return PortError(f"ring.{op}: {type(exc).__name__}")


def _status_error(op: str, response: httpx2.Response) -> PortError:
    code = ""
    payload = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            raw = errors[0].get("code", "")
            code = f" {raw}" if raw else ""
    return PortError(f"ring.{op}: {response.status_code}{code}")
