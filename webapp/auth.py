"""Authentication: Google OAuth ID-token verification + JWT session cookies.

For localhost testing without Google Cloud credentials yet, set
ALLOW_DEMO_LOGIN=1 (default when GOOGLE_CLIENT_ID is unset) to use the demo
login button.
"""
import os
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import HTTPException, Request, Response
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from .database import User

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", "").strip() or secrets.token_hex(32)
JWT_ALGO = "HS256"
COOKIE_NAME = "qx_dashboard_session"
SESSION_TTL_HOURS = 7 * 24
FREE_CREDITS = 120


def demo_enabled() -> bool:
    if os.getenv("ALLOW_DEMO_LOGIN", "").lower() in ("1", "true", "yes"):
        return True
    return not GOOGLE_CLIENT_ID


async def verify_google_id_token(id_token: str) -> dict:
    """Return the verified token claims (sub, email, name, picture)."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google login not configured")
    try:
        info = google_id_token.verify_oauth2_token(
            id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except Exception as e:
        logger.warning("Google token verify failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid Google token")
    if info.get("aud") != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Token audience mismatch")
    return info


def _encode_session(user: User) -> str:
    payload = {
        "sub": user.google_sub,
        "uid": user.id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_session(token: str) -> dict | None:
    if not token:
        return None
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None


def set_session_cookie(response: Response, user: User):
    token = _encode_session(user)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=False,  # localhost/plain http; flip to True behind HTTPS on VPS
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(COOKIE_NAME)


def current_user_id(request: Request) -> int | None:
    token = request.cookies.get(COOKIE_NAME)
    data = decode_session(token)
    return data.get("uid") if data else None