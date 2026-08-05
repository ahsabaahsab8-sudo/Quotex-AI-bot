"""Test the Gmail API OTP flow.

One-time setup: opens browser so you can authorize the app.
After that, token.json stores the refresh token and calls work headless.
"""

import os
import re
import sys
import json
import base64

from dotenv import load_dotenv

load_dotenv()

CLIENT_SECRET_FILE = "client_secret_34679635926-vutum35o4jtdrlc6t1064q6mmm3thujb.apps.googleusercontent.com.json"
TOKEN_FILE = "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES, redirect_uri="http://localhost:51723/"
            )
            creds = flow.run_local_server(port=51723)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"[OK] token saved to {TOKEN_FILE}")
    return build("gmail", "v1", credentials=creds)


def decode_body(msg):
    payload = msg.get("payload", {})
    data = payload.get("body", {}).get("data")
    if data:
        return base64.urlsafe_b64decode(data).decode(errors="ignore")
    for part in payload.get("parts", []):
        d = part.get("body", {}).get("data")
        if d:
            return base64.urlsafe_b64decode(d).decode(errors="ignore")
        if part.get("mimeType") == "text/html":
            d = part.get("body", {}).get("data")
            if d:
                return base64.urlsafe_b64decode(d).decode(errors="ignore")
    return ""


def main():
    query = os.getenv("GMAIL_SEARCH", "from:quotex")
    print(f"[1] Authorizing Gmail API (browser will open if needed)...")
    service = get_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"[OK] Connected as: {profile['emailAddress']}")

    results = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    msgs = results.get("messages", [])
    print(f"[2] Found {len(msgs)} recent email(s) matching '{query}'")
    if not msgs:
        print("    (if you expected emails, try: GMAIL_SEARCH='from:quotex is:unread')")
        return

    for m in msgs:
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in full["payload"]["headers"]}
        subject = headers.get("subject", "?")
        frm = headers.get("from", "?")
        date = headers.get("date", "?")
        body = decode_body(full)
        text = re.sub(r"<[^>]+>", " ", body)
        m = re.search(r"PIN[\s\-]*code\s*:\s*(\d{4,6})", text, re.IGNORECASE)
        if m:
            code = m.group(1)
        else:
            code = "no code found"
        print(f"\n--- {subject} ---")
        print(f"  From: {frm}  |  Date: {date}")
        print(f"  OTP candidate: {code}")
        snippet = re.sub(r"\s+", " ", full.get("snippet", ""))
        print(f"  Snippet: {snippet[:160]}")


if __name__ == "__main__":
    sys.exit(main())
