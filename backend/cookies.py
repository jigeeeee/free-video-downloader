"""Unified cookie source selection for yt-dlp and custom platform modules."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Optional

import config

_copied_cookie_db: Optional[str] = None

PLATFORM_DOMAINS = {
    "youtube": ("youtube.com", "youtu.be", "googlevideo.com"),
    "bilibili": ("bilibili.com", "biliapi.net", "hdslb.com"),
    "douyin": ("douyin.com", "douyinvod.com"),
    "tiktok": ("tiktok.com",),
}

PLATFORM_ENV_KEYS = {
    "youtube": "YTDLP_YOUTUBE_COOKIES_PATH",
    "bilibili": "YTDLP_BILIBILI_COOKIES_PATH",
    "douyin": "YTDLP_DOUYIN_COOKIES_PATH",
    "tiktok": "YTDLP_TIKTOK_COOKIES_PATH",
}


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


def cookie_dir() -> Path:
    path = Path(config.DOWNLOAD_DIR) / "cookies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def platform_from_url_or_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().lower()
    aliases = {
        "youtube": "youtube",
        "yt": "youtube",
        "bilibili": "bilibili",
        "b站": "bilibili",
        "douyin": "douyin",
        "抖音": "douyin",
        "tiktok": "tiktok",
    }
    if text in aliases:
        return aliases[text]
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(domain in text for domain in domains):
            return platform
    return None


def platform_cookie_path(platform: str) -> Path:
    return cookie_dir() / f"{platform}.txt"


def _valid_cookiefile(path: Optional[str | Path]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if p.exists() and p.is_file() and p.stat().st_size > 0:
        return str(p)
    return None


def _generic_cookie_candidates() -> Iterable[str]:
    env_path = os.environ.get("YTDLP_COOKIES_PATH", "")
    if env_path:
        yield env_path
    yield str(Path(config.DOWNLOAD_DIR) / "synced_cookies.txt")
    yield str(config.ROOT_DIR / "cookies.txt")
    yield str(config.ROOT_DIR / "yt-dlp-cookies.txt")


def _platform_cookie_candidates(platform: Optional[str]) -> Iterable[str]:
    if not platform:
        return

    env_key = PLATFORM_ENV_KEYS.get(platform)
    if env_key and os.environ.get(env_key):
        yield os.environ[env_key]

    if platform == "bilibili":
        try:
            from backend.bilibili_auth import get_saved_cookie_path
            qr = get_saved_cookie_path()
            if qr:
                yield qr
        except Exception:
            pass

    yield str(platform_cookie_path(platform))


def get_platform_cookiefiles() -> Dict[str, Optional[str]]:
    return {platform: _valid_cookiefile(platform_cookie_path(platform)) for platform in PLATFORM_DOMAINS}


def get_cookiefile(platform_or_url: Optional[str] = None, *, include_generic: bool = True) -> Optional[str]:
    """Return the best Netscape cookie file for a platform or URL."""
    platform = platform_from_url_or_name(platform_or_url)

    for path in _platform_cookie_candidates(platform):
        valid = _valid_cookiefile(path)
        if valid:
            return valid

    if not platform:
        try:
            from backend.bilibili_auth import get_saved_cookie_path
            qr = get_saved_cookie_path()
            valid = _valid_cookiefile(qr)
            if valid:
                return valid
        except Exception:
            pass

    if include_generic:
        for path in _generic_cookie_candidates():
            valid = _valid_cookiefile(path)
            if valid:
                return valid
    return None


def _apply_browser_cookie_options(opts: dict, browser: str) -> bool:
    browser = browser.strip().lower()
    if not browser:
        return False
    if browser == "chrome":
        db_path = copy_chrome_cookie_db()
        if db_path:
            opts["cookiesfrombrowser"] = ("chrome", "Default", None, db_path)
        else:
            opts["cookiesfrombrowser"] = ("chrome",)
    else:
        opts["cookiesfrombrowser"] = (browser,)
    return True


def apply_cookie_options(opts: dict, url: Optional[str] = None, platform: Optional[str] = None) -> dict:
    """Mutate yt-dlp opts with the configured cookie source."""
    cookie_platform = platform or platform_from_url_or_name(url)

    cookiefile = get_cookiefile(cookie_platform, include_generic=False)
    if cookiefile:
        opts["cookiefile"] = cookiefile
        return opts

    browser = config.COOKIES_BROWSER.strip().lower()
    if _apply_browser_cookie_options(opts, browser):
        return opts

    cookiefile = get_cookiefile(cookie_platform, include_generic=True)
    if cookiefile:
        opts["cookiefile"] = cookiefile
    return opts


def _platforms_for_cookie(domain: str) -> set[str]:
    host = (domain or "").lstrip(".").lower()
    return {
        platform
        for platform, domains in PLATFORM_DOMAINS.items()
        if any(host == d or host.endswith("." + d) for d in domains)
    }


def _write_netscape_cookiefile(output: Path, items: list[dict], header: str) -> int:
    import time

    count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f"# {header}\n\n")
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
            expires_raw = c.get("expirationDate") or c.get("expires")
            try:
                expires = str(int(float(expires_raw))) if expires_raw else str(int(time.time()) + 365 * 86400)
            except Exception:
                expires = str(int(time.time()) + 365 * 86400)
            f.write(f"{domain}\tTRUE\t{c.get('path','/')}\t{secure}\t{expires}\t{name}\t{c.get('value','')}\n")
            count += 1
    return count


def write_synced_cookiefiles(items: list[dict]) -> dict:
    combined = Path(config.DOWNLOAD_DIR) / "synced_cookies.txt"
    total = _write_netscape_cookiefile(combined, items, "Synced by browser extension")

    platforms: Dict[str, dict] = {}
    grouped = {platform: [] for platform in PLATFORM_DOMAINS}
    for item in items:
        if not isinstance(item, dict):
            continue
        for platform in _platforms_for_cookie(item.get("domain", "")):
            grouped[platform].append(item)

    for platform, platform_items in grouped.items():
        output = platform_cookie_path(platform)
        count = _write_netscape_cookiefile(output, platform_items, f"Synced {platform} cookies by browser extension")
        platforms[platform] = {"file": str(output), "count": count, "available": count > 0}

    return {"file": str(combined), "count": total, "platforms": platforms}


def write_synced_cookiefile(items: list[dict]) -> tuple[str, int]:
    result = write_synced_cookiefiles(items)
    return result["file"], result["count"]


def cookie_status() -> dict:
    browser = config.COOKIES_BROWSER.strip() or None
    platforms = {}
    for platform in PLATFORM_DOMAINS:
        platform_file = get_cookiefile(platform, include_generic=False)
        fallback_file = get_cookiefile(platform, include_generic=True)
        source = platform_file or ("browser" if browser else fallback_file)
        platforms[platform] = {
            "cookiefile": platform_file,
            "fallback_cookiefile": fallback_file if fallback_file != platform_file else None,
            "browser": browser,
            "has_cookie_source": bool(source),
        }
    return {
        "browser": browser,
        "generic_cookiefile": get_cookiefile(None),
        "platforms": platforms,
    }
