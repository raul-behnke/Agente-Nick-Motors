"""Auth simples por shared secret (HMAC compare)."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Query

from zoi_agent.config import settings


def require_secret(secret: str = Query(...)) -> None:
    if not hmac.compare_digest(secret, settings.webhook_secret):
        raise HTTPException(status_code=403, detail="invalid secret")
