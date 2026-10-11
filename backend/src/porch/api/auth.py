"""Bearer auth against a stored sha256 of the house key.

Open when house_key_sha256 is None (local replay only); otherwise every
v1 request needs `Authorization: Bearer <key>` matching the hash.
"""

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from porch.api.deps import AppContext, get_ctx

BEARER = "bearer"


def bearer_guard(request: Request, ctx: Annotated[AppContext, Depends(get_ctx)]) -> None:
    """FastAPI dependency raising 401 unless the bearer key matches."""
    expected = ctx.settings.api.house_key_sha256
    if expected is None:
        return
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    candidate = hashlib.sha256(token.encode()).hexdigest() if scheme.lower() == BEARER else ""
    if not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=401, detail="missing or invalid house key")
