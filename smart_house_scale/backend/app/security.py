"""Optional dedicated LAN token for standalone deployment.

When the router is embedded in the existing Smart House API, the host
application should provide its normal authentication dependency instead.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


async def require_optional_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("SMART_HOUSE_SCALE_API_TOKEN")
    if not expected:
        return
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="authentication required")
