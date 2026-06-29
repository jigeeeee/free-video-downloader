"""Unified cookie source selection for yt-dlp and custom platform modules."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import config

_copied_cookie_db: Optional[str] = None


def copy_chrome_cookie_db() -> Optional[str]:
    """Copy Chrome's cookie DB to a temp path so readers avoid SQLite locks."""
    global _copied_cookie_db
    if _copied_cookie_db and Path(_copied_cookie_db).exists():
        return _copied_cookie_db

    localapp = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(localapp) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
        Path(localapp) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
    ]
    for src in candidates:
        if src.exists():
            try:
                tmp = Path(tempfile.gettempdir()) / f"chrome_cookies_{os.getpid()}.db"
                shutil.copy2(str(src), str(tmp))
                _copied_cookie_db = str(tmp)
                return _copied_cookie_db
            except Exception:
                continue
    return None


def get_cookiefile() -> Optional[str]:
    """Return the best Netscape cookie file, ordered by freshness and specificity."""
    env_path = os.environ.get("YTDLP_COOKIES_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = []
    try:
        from backend.bilibili_auth import get_saved_cookie_path
        qr = get_saved_cookie_path()
        if qr:
            candidates.append(qr)
    except Exception:
        pass

    candidates.extend([
        str(Path(config.DOWNLOAD_DIR) / "synced_cookies.txt"),
        str(config.ROOT_DIR / "cookies.txt"),
        str(config.ROOT_DIR / "yt-dlp-cookies.txt"),
    ])

    for path in candidates:
        if path and Path(path).exists() and Path(path).stat().st_size > 0:
            return path
    return None


def apply_cookie_options(opts: dict) -> dict:
    """Mutate yt-dlp opts with the configured cookie source."""
    browser = config.COOKIES_BROWSER.strip().lower()
    if browser == "chrome":
        db_path = copy_chrome_cookie_db()
        if db_path:
            opts["cookiesfrombrowser"] = ("chrome", "Default", None, db_path)
        else:
            cookiefile = get_cookiefile()
            if cookiefile:
                opts["cookiefile"] = cookiefile
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    else:
        cookiefile = get_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
    return opts


def write_synced_cookiefile(items: list[dict]) -> tuple[str, int]:
    import time

    output = Path(config.DOWNLOAD_DIR) / "synced_cookies.txt"
    count = 0
    with output.open("w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# Synced by Chrome extension\n\n")
        for c in items:
            if not isinstance(c, dict):
                continue
            domain = c.get("domain", "")
            name = c.get("name", "")
            if not domain or not name:
                continue
            if not domain.startswith("."):
                domain = "." + domain
            secure = "TRUE" if c.get("secure") else "FALSE"
            expires = str(int(time.time()) + 365 * 86400)
            f.write(f"{domain}\tTRUE\t{c.get('path','/')}\t{secure}\t{expires}\t{name}\t{c.get('value','')}\n")
            count += 1
    return str(output), count
