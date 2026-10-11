"""Ring webhook verification and payload parsing.

Per the docs: every webhook carries an HMAC-SHA256 signature in the
`X-Signature: sha256=<hex>` header, computed over the raw body bytes with
the partner's HMAC signing key. No timestamp is part of the scheme, so
there is no freshness tolerance to enforce; verification is
constant-time.
"""

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from porch.domain import DoorEvent, EventKind

MAX_BODY_BYTES = 64 * 1024
_SIGNATURE_PREFIX = "sha256="


class WebhookSignatureError(Exception):
    """Missing, malformed or mismatched webhook signature."""


def verify_signature(headers: Mapping[str, str], body: bytes, secret: str) -> None:
    """Raise WebhookSignatureError unless the HMAC matches the raw body."""
    received = headers.get("X-Signature") or headers.get("x-signature")
    if not received or not received.startswith(_SIGNATURE_PREFIX):
        msg = "webhook signature missing or malformed"
        raise WebhookSignatureError(msg)
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received.removeprefix(_SIGNATURE_PREFIX)):
        msg = "webhook signature mismatch"
        raise WebhookSignatureError(msg)


def parse_webhook(body: bytes) -> DoorEvent | None:
    """Map a v1.1 payload to DoorEvent; unhandled types return None."""
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return None
    attributes = data.get("attributes", {})
    if not isinstance(attributes, dict):
        return None
    return _door_event(data, attributes)


def _door_event(data: dict[str, Any], attributes: dict[str, Any]) -> DoorEvent | None:
    event_type = data.get("type")
    if event_type == "motion_detected":
        kind: EventKind = "motion"
        sub_type = attributes.get("sub_type")
    elif event_type == "button_press":
        kind = "ding"
        sub_type = None
    else:
        return None
    device_id = attributes.get("source")
    timestamp = attributes.get("timestamp")
    event_id = data.get("id")
    if (
        not isinstance(device_id, str)
        or not isinstance(timestamp, int | float)
        or not isinstance(event_id, str)
    ):
        return None
    return DoorEvent(
        id=event_id,
        device_id=device_id,
        kind=kind,
        sub_type=sub_type if isinstance(sub_type, str) else None,
        start_ms=int(timestamp),
        end_ms=int(timestamp),
        provenance="ring",
    )
