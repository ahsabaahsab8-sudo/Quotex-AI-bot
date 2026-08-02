"""OpenClaw-driven SSID renewal for Quotex.

When the token expires, the bot calls the OpenClaw agent (via the `openclaw`
CLI) to log into Quotex and save a fresh SSID token into session.json.

This module is the OpenClaw path. The old Camoufox / Kameleo / Playwright
methods in renew_ssid.py are kept untouched and act as fallbacks.
"""

import os
import json
import shutil
import asyncio
import tempfile
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
PROMPT_FILE = BASE_DIR / "prompt.md"
SESSION_FILE = BASE_DIR / "session.json"

OPENCLAW_CMD = os.environ.get("OPENCLAW_CMD", "")
OPENCLAW_AGENT = os.environ.get("OPENCLAW_AGENT", "main")
OPENCLAW_TIMEOUT = int(os.environ.get("OPENCLAW_TIMEOUT", "900"))


def load_session_data() -> dict:
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def current_token() -> str | None:
    data = load_session_data()
    email = os.getenv("QUOTEX_EMAIL", "")
    if email in data:
        return data[email].get("token")
    for key in ("", "null"):
        if key in data and isinstance(data[key], dict):
            return data[key].get("token")
    for val in data.values():
        if isinstance(val, dict) and val.get("token"):
            return val["token"]
    return None


def _find_openclaw() -> str | None:
    if OPENCLAW_CMD and Path(OPENCLAW_CMD).exists():
        return OPENCLAW_CMD
    found = shutil.which("openclaw")
    if found:
        return found
    # npm global shims on Windows/Linux
    for cand in (
        Path.home() / "AppData" / "Roaming" / "npm" / "openclaw.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "openclaw",
        Path.home() / ".npm-global" / "bin" / "openclaw",
        Path("/usr/local/bin") / "openclaw",
    ):
        if cand.exists():
            return str(cand)
    return None


def _render_prompt() -> str:
    """Render prompt.md template with this machine's real paths + email."""
    text = PROMPT_FILE.read_text(encoding="utf-8")
    email = os.getenv("QUOTEX_EMAIL", "")
    return text.replace("{{PROJECT_DIR}}", str(BASE_DIR)).replace("{{EMAIL}}", email)


def _write_temp_prompt() -> Path:
    fd, tmp = tempfile.mkstemp(prefix="openclaw_prompt_", suffix=".md")
    os.close(fd)
    path = Path(tmp)
    path.write_text(_render_prompt(), encoding="utf-8")
    return path


async def renew_via_openclaw(timeout: int | None = None) -> str | None:
    """Run the OpenClaw agent to refresh the SSID token.

    Returns the new token (also written into session.json by the agent),
    or None on failure.
    """
    timeout = timeout or OPENCLAW_TIMEOUT

    if not PROMPT_FILE.exists():
        logger.error("OpenClaw prompt file missing: %s", PROMPT_FILE)
        return None

    exe = _find_openclaw()
    if not exe:
        logger.error("openclaw CLI not found (set OPENCLAW_CMD in .env)")
        return None

    old_token = current_token()
    logger.info("OpenClaw: renewing SSID via agent %s (timeout=%ss)...", OPENCLAW_AGENT, timeout)

    tmp_prompt = _write_temp_prompt()
    session_key = f"agent:{OPENCLAW_AGENT}:quotex-renew"
    cmd = [
        exe, "agent",
        "--agent", OPENCLAW_AGENT,
        "--session-key", session_key,
        "--message-file", str(tmp_prompt),
        "--timeout", str(timeout),
        "--json",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 60)
    except asyncio.TimeoutError:
        logger.error("OpenClaw renewal timed out after %ss", timeout + 60)
        proc.kill()
        await proc.wait()
        tmp_prompt.unlink(missing_ok=True)
        return None

    tmp_prompt.unlink(missing_ok=True)

    if proc.returncode != 0:
        err_text = stderr.decode("utf-8", errors="replace")[-800:]
        logger.warning("openclaw exited code %s: %s", proc.returncode, err_text)

    # Give the agent a moment to finish writing session.json
    for _ in range(10):
        new_token = current_token()
        if new_token and new_token != old_token:
            logger.info("OpenClaw renewal SUCCESS: %s...%s", new_token[:8], new_token[-4:])
            return new_token
        await asyncio.sleep(3)

    logger.error("OpenClaw renewal FAILED: token unchanged in session.json")
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tok = asyncio.run(renew_via_openclaw())
    if tok:
        print(f"SUCCESS: {tok[:12]}...{tok[-4:]}")
    else:
        print("FAILED")
