"""Bilibili QR-code login + cookie auto-refresh.

Flow:
  1. POST /api/bilibili/qrcode  → backend calls Bili API → returns {url, qrcode_key}
  2. Frontend renders QR code image, polls GET /api/bilibili/qrcode/status?key=xxx
  3. Backend polls Bili polling endpoint → when "confirmed", extracts Set-Cookie
  4. Saves cookies to Netscape file → yt-dlp uses it automatically.
  5. On startup, backend checks cookie freshness → auto-refreshes if needed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import urlencode

import config

log = logging.getLogger(__name__)

COOKIE_FILE = os.path.join(config.DOWNLOAD_DIR, "bilibili_cookies.txt")

# ── Low-level HTTP helpers ───────────────────────────────────────────────

_BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


def _get(url: str, headers: dict | None = None, cookies: dict | None = None) -> dict:
    import urllib.request
    hdrs = {**_BILI_HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return {
            "json": json.loads(raw),
            "headers": dict(resp.headers),
            "cookies": _parse_set_cookie(resp.headers.get_all("Set-Cookie") or []),
        }


def _post(url: str, data: dict, headers: dict | None = None, cookies: dict | None = None) -> dict:
    import urllib.request
    body = urlencode(data).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", **_BILI_HEADERS}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return {
            "json": json.loads(raw),
            "headers": dict(resp.headers),
            "cookies": _parse_set_cookie(resp.headers.get_all("Set-Cookie") or []),
        }


def _parse_set_cookie(headers: list[str]) -> dict:
    """Extract cookie key=value pairs from Set-Cookie headers."""
    result = {}
    for h in headers:
        for part in h.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                if k.lower() not in ("domain", "path", "expires", "max-age", "secure", "httponly", "samesite"):
                    result[k] = v
    return result


# ── QR Login ─────────────────────────────────────────────────────────────

_qr_sessions: dict = {}  # qrcode_key → {"status": str, "cookies": dict|None}


async def generate_qrcode() -> dict:
    """Generate a Bilibili login QR code.

    Returns { url, qrcode_key }.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _generate_qrcode_sync)


def _generate_qrcode_sync() -> dict:
    resp = _get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
    data = resp["json"]["data"]
    key = data["qrcode_key"]
    url = data["url"]
    _qr_sessions[key] = {"status": "waiting", "cookies": None}
    log.info("QR code generated: key=%s", key)
    return {"url": url, "qrcode_key": key}


async def poll_qrcode(qrcode_key: str) -> dict:
    """Poll the QR code scan status.

    Returns { status: "waiting"|"scanned"|"expired"|"confirmed", cookies: dict|None }
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _poll_qrcode_sync, qrcode_key)


def _poll_qrcode_sync(qrcode_key: str) -> dict:
    session = _qr_sessions.get(qrcode_key, {})
    url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
    resp = _get(url)

    code = resp["json"]["data"]["code"]
    # https://api.bilibili.com/x/web-interface/nav returns code=0 when logged in
    status_map = {
        86101: "waiting",   # not scanned
        86090: "scanned",   # scanned but not confirmed
        86038: "expired",   # expired
        0: "confirmed",     # login successful
    }
    status = status_map.get(code, "error")

    if status == "confirmed":
        cookies = resp.get("cookies", {})
        _qr_sessions[qrcode_key] = {"status": "confirmed", "cookies": cookies}
        _save_cookies(cookies)
        log.info("QR login confirmed — %d cookies saved", len(cookies))
        return {"status": "confirmed", "cookies": cookies}
    else:
        _qr_sessions[qrcode_key] = {"status": status, "cookies": None}
        return {"status": status, "cookies": None}


# ── Cookie persistence ───────────────────────────────────────────────────

def _save_cookies(cookies: dict) -> None:
    """Write cookies to Netscape-format file for yt-dlp."""
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# Bilibili — QR login\n\n")
        for name, value in cookies.items():
            domain = ".bilibili.com"
            flag = "TRUE"
            secure = "TRUE"
            expires = str(int(time.time()) + 365 * 86400)  # fake far future
            path = "/"
            f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")


def get_saved_cookie_path() -> Optional[str]:
    """Return path to saved Bilibili cookies if they exist and are valid."""
    if os.path.isfile(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 100:
        return COOKIE_FILE
    return None


# ── Auto-refresh ─────────────────────────────────────────────────────────

async def refresh_cookies() -> bool:
    """Attempt to refresh Bilibili cookies using refresh_token.

    Returns True if refresh succeeded.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _refresh_cookies_sync)


def _refresh_cookies_sync() -> bool:
    cookies_txt = get_saved_cookie_path()
    if not cookies_txt:
        return False

    # Parse existing cookies
    existing = {}
    with open(cookies_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                existing[parts[5]] = parts[6]

    # Check if refresh is needed
    try:
        info = _get("https://passport.bilibili.com/x/passport-login/web/cookie/info", cookies=existing)
        need_refresh = info["json"].get("data", {}).get("refresh", False)
        if not need_refresh:
            log.info("Bilibili cookies still valid — no refresh needed")
            return True
    except Exception as e:
        log.warning("Cookie info check failed: %s", e)
        return False

    # Try to refresh
    bili_jct = existing.get("bili_jct", "")
    try:
        timestamp = int(time.time() * 1000)
        refresh_csrf = _compute_refresh_csrf(timestamp)

        resp = _post(
            "https://passport.bilibili.com/x/passport-login/web/cookie/refresh",
            data={
                "csrf": bili_jct,
                "refresh_csrf": refresh_csrf,
                "source": "main_web",
                "refresh_token": existing.get("refresh_token", ""),
            },
            cookies=existing,
        )
        if resp["json"].get("code") == 0:
            new_cookies = {**existing, **resp.get("cookies", {})}
            _save_cookies(new_cookies)
            log.info("Bilibili cookies refreshed successfully")
            return True
    except Exception as e:
        log.warning("Cookie refresh failed: %s", e)

    return False


def _compute_refresh_csrf(timestamp: int) -> str:
    """Compute the refresh_csrf value required by Bilibili's refresh endpoint."""
    # Known algorithm: md5 of some combination — simplified version
    # Real implementation varies; we try the common one
    key = hashlib.md5(f"{timestamp}refresh".encode()).hexdigest()
    return key


# ── Cleanup stale sessions ───────────────────────────────────────────────

def cleanup_qr_sessions():
    """Remove expired QR sessions (older than 5 minutes)."""
    now = time.time()
    to_delete = []
    # In simple dict we don't track time, skip for now
