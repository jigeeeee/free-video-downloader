"""Douyin video downloader using XBogus + ABogus signing (no yt-dlp needed)."""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlencode

import requests

from backend.douyin.xbogus import XBogus
from backend.douyin.abogus import ABogus, BrowserFingerprintGenerator

logger = logging.getLogger("douyin")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

BASE_URL = "https://www.douyin.com"
DETAIL_API = "/aweme/v1/web/aweme/detail/"

_xb = XBogus(UA)
_fp = BrowserFingerprintGenerator.generate_fingerprint("Chrome")
_ab = ABogus(fp=_fp, user_agent=UA)


def _get_cookies() -> Dict[str, str]:
    cookies = {}
    cookie_file = None
    for name in ["cookies.txt", "yt-dlp-cookies.txt"]:
        p = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / name
        if p.exists():
            cookie_file = p
            break
    if not cookie_file:
        return cookies

    with open(cookie_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0]
                name = parts[5]
                value = parts[6]
                if "douyin.com" in domain:
                    cookies[name] = value
    return cookies


def _sign_url(path: str, params: Dict) -> str:
    query = urlencode(params)
    base = f"{BASE_URL}{path}"
    ab_params, abogus, ua2, _ = _ab.generate_abogus(query, "")
    return f"{base}?{ab_params}", ua2


def extract_video_id(url: str) -> Optional[str]:
    # /video/123 or /jingxuan?modal_id=123 or /user/xxx?modal_id=123
    m = re.search(r'/video/(\d{15,20})', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]modal_id=(\d{15,20})', url)
    if m:
        return m.group(1)
    return None


def extract_info(url: str) -> dict:
    video_id = extract_video_id(url)
    if not video_id:
        raise RuntimeError(f"Cannot extract video ID from URL: {url}")

    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "aweme_id": video_id,
        "update_version_code": "170400",
        "pc_client_type": "1",
        "pc_libra_divert": "Windows",
        "version_code": "290100",
        "version_name": "29.1.0",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "131.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "131.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "16",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "200",
    }

    signed_url, ua = _sign_url(DETAIL_API, params)
    cookies = _get_cookies()

    headers = {
        "User-Agent": ua,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    resp = requests.get(signed_url, headers=headers, cookies=cookies, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Douyin API returned HTTP {resp.status_code}")

    if not resp.text or not resp.text.strip():
        if not cookies:
            raise RuntimeError("Douyin requires cookies. Export cookies.txt from browser (login to douyin.com).")
        raise RuntimeError("Douyin API returned empty response. Cookies may be expired. Re-export cookies.txt.")

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Douyin returned non-JSON response (length={len(resp.text)})")

    aweme_detail = data.get("aweme_detail")
    if not aweme_detail:
        if not cookies:
            raise RuntimeError("Douyin requires cookies. Export cookies.txt from your browser (logged into douyin.com).")
        raise RuntimeError(f"Douyin returned empty data. Cookies may be expired. Status: {data.get('status_code')}")

    video = aweme_detail.get("video", {})
    play_addr = video.get("play_addr", {}) or {}
    formats = []

    url_list = play_addr.get("url_list", [])
    # Also get best quality from bit_rate
    bit_rate = video.get("bit_rate", [])
    best_video_url = None
    if bit_rate:
        best = bit_rate[0]
        best_pa = best.get("play_addr", {}) or {}
        best_urls = best_pa.get("url_list", [])
        if best_urls:
            best_video_url = best_urls[0]
            url_list = best_urls  # Use best quality

    if url_list:
        gear = bit_rate[0].get("gear_name", "auto") if bit_rate else "auto"
        formats.append({
            "format_id": "play_addr",
            "resolution": gear,
            "ext": "mp4",
            "filesize": None,
            "filesize_str": None,
            "fps": None,
            "codec": "h264",
            "video_only": True,
        })

    dur = aweme_detail.get("duration", 0)
    dur = int(dur / 1000) if dur else 0
    dur_str = None
    if dur:
        m, s = divmod(dur, 60)
        h, m = divmod(m, 60)
        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    cover = aweme_detail.get("video", {}).get("cover", {})
    thumb_list = cover.get("url_list", [])
    thumb = thumb_list[0] if thumb_list else None

    author = aweme_detail.get("author", {}) or {}
    nickname = author.get("nickname", "")

    # All CDN URLs (3 backup URLs from Douyin)
    video_urls = [u.replace("\\u0026", "&") for u in url_list] if url_list else []

    # Audio URL (separate track for Douyin)
    music = aweme_detail.get("music", {}) or {}
    music_play = music.get("play_url", {}) or {}
    music_urls_raw = music_play.get("url_list", [])
    audio_urls = [u.replace("\\u0026", "&") for u in music_urls_raw] if music_urls_raw else []

    return {
        "title": aweme_detail.get("desc", "Unknown") or f"Douyin {video_id}",
        "thumbnail": thumb,
        "duration": dur,
        "duration_str": dur_str,
        "platform": "Douyin",
        "uploader": nickname,
        "formats": formats,
        "webpage_url": f"https://www.douyin.com/video/{video_id}",
        "_video_urls": video_urls,
        "_audio_urls": audio_urls,
    }

