"""Fetch the latest Quotex OTP pincode via the Gmail API.

Replaces the IMAP reader (imap_proxy + IMAP_PASSWORD). Auth is OAuth2 via
client_secret JSON + a stored refresh token (gmail_token.json), so no app
password is needed and Gmail can't rate-limit/block IMAP basic auth.

Only returns the *latest* code from a genuine Quotex ("Authentication
pincode") email that arrived after the requested time, and every code is
consumed once (module-level message-id tracker) so a stale code from an
earlier login attempt is never resubmitted.
"""

import os
import re
import time
import base64
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CLIENT_SECRET_FILE = os.path.join(
    os.path.dirname(__file__),
    "client_secret_34679635926-vutum35o4jtdrlc6t1064q6mmm3thujb.apps.googleusercontent.com.json",
)
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "gmail_token.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Gmail message IDs of OTP emails already consumed, so a code is only
# submitted once across renewal attempts.
_consumed_ids: set[str] = set()

_service = None


def get_service():
    """Build (and cache) the Gmail API service, refreshing the token if needed."""
    global _service
    if _service is not None:
        return _service
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "No valid Gmail OAuth token. Run test_gmail_api.py once to authorize."
            )
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    _service = build("gmail", "v1", credentials=creds)
    return _service


def _decode_body(msg) -> str:
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="ignore")
    for part in payload.get("parts", []):
        d = part.get("body", {}).get("data")
        if d:
            return base64.urlsafe_b64decode(d).decode(errors="ignore")
    return ""


def _extract_otp(text: str) -> str | None:
    """Extract the real PIN from a Quotex 'Authentication pincode' email.

    The email is HTML-only and its first 4-6 digit string is '1999' (from the
    xhtml doctype), so a naive regex returns the wrong code. Anchor on the
    'PIN-code' label instead, tolerating HTML tags between words.
    """
    if not text:
        return None
    body = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE)
    visible = re.sub(r"<[^>]+>", " ", body)
    m = re.search(
        r"(?:pin[-\s]?code|authentication\s*pin|verification\s*cod?e)"
        r"[^0-9]{0,80}?(\d{4,6})",
        visible, re.IGNORECASE,
    )
    if m:
        code = m.group(1)
        if re.fullmatch(r"\d{4,6}", code):
            return code
    return None


def fetch_latest_otp(timeout: int = 120, since=None) -> str | None:
    """Poll Gmail for the newest genuine Quotex pincode.

    `since` is a naive-UTC datetime; only emails sent after it are accepted.
    Polls every 2s until the timeout so a brand-new email is picked up even
    while Gmail's search index is still catching up.
    """
    global _consumed_ids
    lower = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=20)
    if since is not None and since > lower:
        lower = since
    deadline = time.time() + timeout
    seen_ids = set()

    try:
        service = get_service()
    except Exception as e:
        logger.warning("Gmail API auth failed: %s", e)
        return None

    while time.time() < deadline:
        try:
            results = service.users().messages().list(
                userId="me", q="from:quotex", maxResults=10
            ).execute()
            for m in results.get("messages", []):
                mid = m["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                if mid in _consumed_ids:
                    continue
                full = service.users().messages().get(
                    userId="me", id=mid, format="full"
                ).execute()
                headers = {h["name"].lower(): h["value"]
                           for h in full["payload"].get("headers", [])}
                if "quotex" not in headers.get("from", "").lower():
                    continue
                subject = headers.get("subject", "")
                if "pin" not in subject.lower() and "code" not in subject.lower() \
                        and "authentication" not in subject.lower():
                    continue
                try:
                    from email.utils import parsedate_to_datetime
                    sent = parsedate_to_datetime(headers.get("date", ""))
                    if sent is None or sent.replace(tzinfo=None) < lower:
                        continue
                except Exception:
                    continue
                otp = _extract_otp(_decode_body(full))
                if otp:
                    _consumed_ids.add(mid)
                    logger.info("Gmail OTP: code %s from %s", otp, subject)
                    return otp
        except Exception as e:
            logger.warning("Gmail API read failed: %s", e)
        time.sleep(2)

    logger.warning("Gmail OTP: no fresh Quotex pincode after %ds", timeout)
    return None


def reset_consumed():
    """Clear the consumed-message tracker (used by tests)."""
    global _consumed_ids
    _consumed_ids = set()
