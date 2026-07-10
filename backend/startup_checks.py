"""Startup diagnostics for optional runtime dependencies."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any, Dict, List

import config


def run_startup_checks() -> Dict[str, Any]:
    required = ["fastapi", "uvicorn", "yt_dlp", "dotenv", "aiohttp", "openai", "requests", "gmssl"]
    optional = ["whisper"]
    missing_required: List[str] = [name for name in required if importlib.util.find_spec(name) is None]
    missing_optional: List[str] = [name for name in optional if importlib.util.find_spec(name) is None]
    ffmpeg_path = shutil.which("ffmpeg")
    node_path = shutil.which("node")
    cookie_info = _detect_cookie_status()
    cookiefile = cookie_info.get("generic_cookiefile")
    warnings = []
    if not ffmpeg_path:
        warnings.append("ffmpeg not found in PATH; merging, conversion, and Whisper may fail.")
    if not node_path:
        warnings.append("node not found in PATH; some YouTube JavaScript challenges may fail.")
    platform_sources = cookie_info.get("platforms", {})
    has_any_platform_source = any(item.get("has_cookie_source") for item in platform_sources.values())
    if not cookiefile and not config.COOKIES_BROWSER.strip() and not has_any_platform_source:
        warnings.append("No cookie file detected; restricted Bilibili/Douyin/YouTube videos may fail.")
    return {
        "ok": not missing_required,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "ffmpeg": ffmpeg_path,
        "node": node_path,
        "cookies": {
            "browser": config.COOKIES_BROWSER.strip() or None,
            "cookiefile": cookiefile,
            "has_cookie_source": bool(cookiefile or config.COOKIES_BROWSER.strip() or has_any_platform_source),
            "platforms": platform_sources,
        },
        "youtube": {
            "po_token_configured": bool(config.YOUTUBE_PO_TOKEN.strip()),
            "visitor_data_configured": bool(config.YOUTUBE_VISITOR_DATA.strip()),
        },
        "ai": {
            "deepseek_api_key_configured": bool(getattr(config, "DEEPSEEK_API_KEY", "").strip()),
        },
        "warnings": warnings,
    }


def _detect_cookiefile() -> str | None:
    try:
        from backend.cookies import get_cookiefile
        cookiefile = get_cookiefile()
        if cookiefile:
            return cookiefile
    except Exception:
        pass

    for candidate in (
        Path(config.DOWNLOAD_DIR) / "synced_cookies.txt",
        config.ROOT_DIR / "cookies.txt",
        config.ROOT_DIR / "yt-dlp-cookies.txt",
    ):
        if candidate.exists() and candidate.stat().st_size > 0:
            return str(candidate)
    return None


def _detect_cookie_status() -> dict:
    try:
        from backend.cookies import cookie_status
        return cookie_status()
    except Exception:
        return {"browser": config.COOKIES_BROWSER.strip() or None, "generic_cookiefile": _detect_cookiefile(), "platforms": {}}
