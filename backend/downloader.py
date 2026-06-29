"""yt-dlp download engine wrapper — auto-copies Chrome cookie DB to avoid lock."""

import asyncio
import os
import sys
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor

import config
from backend.cookies import apply_cookie_options, copy_chrome_cookie_db, get_cookiefile
from backend.media import safe_filename

tasks: Dict[str, dict] = {}

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_YOUTUBE_CLIENTS = [None, "web_safari", "ios", "android", "android_vr", "tv"]

logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)

# Cache copied cookie DB path for the session
_copied_cookie_db: Optional[str] = None


def _copy_chrome_cookie_db() -> Optional[str]:
    """Copy Chrome's cookie SQLite DB to a temp file (avoids lock)."""
    return copy_chrome_cookie_db()


def _get_cookiefile() -> Optional[str]:
    return get_cookiefile()


def _normalize_url(url: str) -> str:
    url = url.strip()
    # Douyin: /user/X?modal_id=Y, /jingxuan?modal_id=Y, /video/Y
    m = re.search(r'douyin\.com/\S+\?.*modal_id=(\d{15,20})', url)
    if m:
        return f"https://www.douyin.com/video/{m.group(1)}"
    if "bilibili.com" in url and not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    m = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)', url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def _youtube_extractor_args(client: Optional[str] = None) -> Optional[dict]:
    youtube_args = {}
    if client:
        youtube_args["player_client"] = [client]
    if config.YOUTUBE_PO_TOKEN:
        youtube_args["po_token"] = [config.YOUTUBE_PO_TOKEN.strip()]
    if config.YOUTUBE_VISITOR_DATA:
        youtube_args["visitor_data"] = [config.YOUTUBE_VISITOR_DATA.strip()]
    return {"youtube": youtube_args} if youtube_args else None


def _youtube_strategy_label(client: Optional[str]) -> str:
    return client or "default"


def _build_opts(extra: dict = None, extractor_args: dict = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "no_playlist": True,
        "extract_flat": False,
        "socket_timeout": 60,
        "retries": 20,
        "fragment_retries": 20,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "continuedl": True,
        "http_headers": _BROWSER_HEADERS,
        "logger": logging.getLogger("yt_dlp"),
    }
    if extractor_args:
        opts["extractor_args"] = extractor_args

    apply_cookie_options(opts)

    if extra:
        opts.update(extra)
    return opts


def _is_auth_error(msg: str) -> bool:
    tests = ["412", "403", "Forbidden", "Sign in to confirm", "not a bot", "Precondition Failed", "Fresh cookies"]
    return any(t in msg for t in tests)


def _is_drm_error(msg: str) -> bool:
    text = (msg or "").lower()
    return "drm protected" in text or "drm-protected" in text


def _format_drm_error(platform: str = "YouTube") -> str:
    return (
        f"{platform} reports this video is DRM protected. "
        "This downloader cannot bypass DRM or download protected streams. "
        "Please choose a non-DRM video or use the platform's official offline/download option if available."
    )


def _is_download_retryable_error(msg: str) -> bool:
    if _is_drm_error(msg):
        return False
    tests = [
        "403", "Forbidden", "HTTP Error", "unable to download video data",
        "Fresh cookies", "Sign in", "not a bot", "Requested format is not available",
        "This video is unavailable", "timed out", "timeout", "ReadTimeout",
        "ConnectionError", "HTTPSConnectionPool", "Max retries exceeded",
        "Connection aborted", "Connection reset", "RemoteDisconnected",
        "Temporary failure", "NameResolutionError", "SSLError",
    ]
    return any(t.lower() in (msg or "").lower() for t in tests)


def _clean_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _format_cookie_help(platform: str) -> str:
    return (f"\n\n[{platform}] Requires browser cookies."
            f"\n  Make sure you are logged into {platform} in Chrome."
            f"\n  Or: export cookies.txt to {config.ROOT_DIR / 'cookies.txt'}")


def _format_youtube_failure(last_error: str, requested_format: Optional[dict] = None) -> str:
    requested = ""
    if requested_format:
        resolution = requested_format.get("resolution") or "selected quality"
        ext = requested_format.get("ext") or ""
        requested = f"The selected {resolution} {ext} format was not downgraded.\n"
    return (
        "YouTube download failed after trying multiple clients and fallback formats.\n"
        f"{requested}"
        f"Last error: {last_error}\n\n"
        "Try updating yt-dlp, syncing fresh browser cookies, or configuring "
        "YTDLP_YOUTUBE_PO_TOKEN and YTDLP_YOUTUBE_VISITOR_DATA in .env."
    )


def extract_info(url: str) -> dict:
    url = _normalize_url(url)
    platform = _detect_platform(url)

    # Douyin: use dedicated API with XBogus + ABogus signing
    if platform == "Douyin":
        try:
            from backend.douyin.api import extract_info as douyin_extract_info
            return douyin_extract_info(url)
        except ImportError as e:
            raise RuntimeError(f"Douyin module not available: {e}")
        except Exception as e:
            raise RuntimeError(str(e))

    import yt_dlp

    last_error = None
    clients = _YOUTUBE_CLIENTS if platform == "YouTube" else [None]

    for client in clients:
        try:
            extractor_args = _youtube_extractor_args(client) if platform == "YouTube" else None
            with yt_dlp.YoutubeDL(_build_opts(extractor_args=extractor_args)) as ydl:
                info = ydl.extract_info(url, download=False)
            if info:
                return _parse_info(info, url)
        except Exception as e:
            last_error = _clean_ansi(str(e))
            if _is_drm_error(last_error):
                raise RuntimeError(_format_drm_error(platform))
            if not _is_auth_error(last_error):
                raise RuntimeError(last_error)
            continue

    raise RuntimeError(f"{last_error}{_format_cookie_help(platform)}")


def _parse_info(info: dict, url: str) -> dict:
    formats = []
    seen = set()
    raw = [f for f in (info.get("formats") or []) if f and f.get("ext") != "mhtml"]

    for f in raw:
        res = f.get("resolution") or f.get("format_note") or ""
        h = f.get("height") or 0
        if h >= 2160: res = "4K"
        elif h >= 1080: res = "1080p"
        elif h >= 720: res = "720p"
        elif h >= 480: res = "480p"
        elif not res:
            res = "audio only" if f.get("acodec") != "none" and f.get("vcodec") == "none" else "other"

        key = f"{res}_{f.get('ext','')}"
        if key in seen: continue
        seen.add(key)

        fs = f.get("filesize") or f.get("filesize_approx")
        fs_str = _format_size(fs) if fs else None

        vcodec = f.get("vcodec") or ""
        acodec = f.get("acodec") or ""
        is_video_only = vcodec != "none" and vcodec and acodec == "none"

        formats.append({
            "format_id": f.get("format_id", ""),
            "resolution": res,
            "ext": f.get("ext", ""),
            "filesize": fs,
            "filesize_str": fs_str,
            "fps": f.get("fps"),
            "codec": vcodec or acodec,
            "video_only": is_video_only,
        })

    order = {"4K": 0, "1080p": 1, "720p": 2, "480p": 3}
    formats.sort(key=lambda x: order.get(x["resolution"], 99))

    dur = info.get("duration")
    dur_str = None
    if dur:
        m, s = divmod(int(dur), 60)
        h, m = divmod(m, 60)
        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    wurl = info.get("webpage_url", url)
    thumb = info.get("thumbnail")
    # Bilibili CDN returns http:// thumbnails — force https for browser compatibility
    if thumb and isinstance(thumb, str) and thumb.startswith("http://") and "hdslb.com" in thumb:
        thumb = thumb.replace("http://", "https://", 1)
    return {
        "title": info.get("title", "Unknown"),
        "thumbnail": thumb,
        "duration": dur,
        "duration_str": dur_str,
        "platform": _detect_platform(wurl),
        "uploader": info.get("uploader"),
        "formats": formats,
        "webpage_url": wurl,
    }


def _format_size(b: int) -> str:
    if not b: return "?"
    if b >= 1_000_000_000: return f"{b/1_000_000_000:.1f} GB"
    if b >= 1_000_000: return f"{b/1_000_000:.1f} MB"
    if b >= 1_000: return f"{b/1_000:.1f} KB"
    return f"{b} B"


def _newest_media_file(since_ts: float, marker: Optional[str] = None) -> Optional[Path]:
    exts = {".mp4", ".webm", ".mkv", ".mov"}
    root = Path(config.DOWNLOAD_DIR)
    candidates = [
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in exts and p.stat().st_mtime >= since_ts - 1
    ]
    if marker:
        candidates = [p for p in candidates if marker in p.name]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u: return "YouTube"
    if "bilibili.com" in u: return "Bilibili"
    # Be precise: douyinvod.com (CDN) is NOT douyin.com (platform)
    if "www.douyin.com" in u: return "Douyin"
    if "/douyin.com/video" in u: return "Douyin"
    if "twitter.com" in u or "x.com" in u: return "Twitter/X"
    if "tiktok.com" in u: return "TikTok"
    if "instagram.com" in u: return "Instagram"
    if "vimeo.com" in u: return "Vimeo"
    if "facebook.com" in u: return "Facebook"
    return "Other"


def _height_from_format(fmt: Optional[dict]) -> Optional[int]:
    if not fmt:
        return None
    resolution = str(fmt.get("resolution") or "")
    match = re.search(r"(\d{3,4})p", resolution)
    if match:
        return int(match.group(1))
    match = re.search(r"\d+x(\d+)", resolution)
    if match:
        return int(match.group(1))
    return None


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _format_candidates(format_id: str, requested_format: Optional[dict], platform: str) -> List[str]:
    selected = format_id or "bestvideo+bestaudio/best"
    candidates = [selected]

    if (
        platform != "Douyin"
        and "+" not in selected
        and selected not in ("best", "bestvideo+bestaudio", "bestvideo+bestaudio/best")
        and requested_format
        and requested_format.get("video_only")
    ):
        candidates[0] = f"{selected}+bestaudio"

    if platform == "YouTube":
        if requested_format and str(requested_format.get("resolution", "")).lower().startswith("audio"):
            candidates.append("bestaudio")
        if not requested_format:
            candidates.extend(["bestvideo+bestaudio/best", "best"])

    return _dedupe(candidates)


def _downloaded_format_matches(path: Path, task_id: str, requested_format: Optional[dict]) -> bool:
    if not requested_format:
        return True
    requested_id = str(requested_format.get("format_id") or "")
    if not requested_id:
        return True
    match = re.search(rf"\[{re.escape(task_id)}-[^\]]+-(?P<format_id>[^\]]+)\]", path.name)
    if not match:
        return False
    downloaded_id = match.group("format_id")
    downloaded_parts = set(downloaded_id.split("+"))
    return requested_id in downloaded_parts


async def _download_direct(direct_url: str, task_id: str) -> None:
    """Download a video from a direct URL using HTTP streaming."""
    import aiohttp
    import time

    tasks[task_id] = {
        "task_id": task_id, "status": "downloading", "percent": 0.0,
        "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": None,
    }

    # Derive filename from URL
    url_path = direct_url.split("?")[0]
    fn = safe_filename(os.path.basename(url_path) or f"douyin_{task_id}.mp4", f"douyin_{task_id}.mp4")
    if not fn.endswith(".mp4"):
        fn += ".mp4"
    out_path = os.path.join(config.DOWNLOAD_DIR, fn)
    tasks[task_id]["filename"] = fn

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.douyin.com/",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(direct_url, headers=headers, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")

                total = resp.content_length or 0
                if total:
                    tasks[task_id]["filesize_str"] = _format_size(total)

                downloaded = 0
                start_time = time.time()
                with open(out_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = round(downloaded / total * 100, 1)
                            tasks[task_id]["percent"] = pct
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                speed = downloaded / elapsed
                                tasks[task_id]["speed"] = _format_size(int(speed)) + "/s"
                                if pct > 0:
                                    eta_sec = (total - downloaded) / speed
                                    m, s = divmod(int(eta_sec), 60)
                                    tasks[task_id]["eta"] = f"{m}:{s:02d}"

        tasks[task_id]["status"] = "done"
        tasks[task_id]["percent"] = 100.0
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)

async def _download_douyin_merged(video_url: str, audio_url: str, task_id: str) -> None:
    """Download Douyin video + audio separately, then merge with ffmpeg."""
    import aiohttp
    import ssl
    import time
    import traceback as _tb

    tasks[task_id] = {
        "task_id": task_id, "status": "downloading", "percent": 0.0,
        "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": None,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
    }

    # Douyin returns multiple CDN URLs; try them in order
    video_urls = [video_url] if isinstance(video_url, str) else (video_url or [])
    audio_urls = [audio_url] if isinstance(audio_url, str) else (audio_url or [])

    video_path = os.path.join(config.DOWNLOAD_DIR, f"_video_{task_id}.mp4")
    audio_path = os.path.join(config.DOWNLOAD_DIR, f"_audio_{task_id}.mp3")
    out_fn = safe_filename(f"douyin_{task_id}.mp4")
    out_path = os.path.join(config.DOWNLOAD_DIR, out_fn)
    tasks[task_id]["filename"] = out_fn

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Download video (80% of progress)
            video_ok = False
            last_err = None
            for i, vurl in enumerate(video_urls):
                try:
                    async with session.get(
                        vurl, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120),
                        ssl=ssl_ctx
                    ) as resp:
                        if resp.status != 200:
                            last_err = f"Video CDN[{i}] HTTP {resp.status}"
                            continue
                        total_v = resp.content_length or 0
                        if total_v:
                            tasks[task_id]["filesize_str"] = _format_size(total_v)
                        downloaded = 0
                        start_t = time.time()
                        with open(video_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(65536):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_v > 0:
                                    pct = round(downloaded / total_v * 80, 1)
                                    tasks[task_id]["percent"] = pct
                                if downloaded > 0 and time.time() - start_t > 0:
                                    spd = downloaded / (time.time() - start_t)
                                    tasks[task_id]["speed"] = _format_size(int(spd)) + "/s"
                        video_ok = True
                        break
                except asyncio.TimeoutError:
                    last_err = f"Video CDN[{i}] timeout"
                    continue
                except Exception as e:
                    last_err = f"Video CDN[{i}]: {e}"
                    continue

            if not video_ok:
                raise RuntimeError(f"All video CDNs failed: {last_err}")

            # 2. Download audio (20% of progress)
            has_audio = False
            if audio_urls:
                for i, aurl in enumerate(audio_urls):
                    try:
                        async with session.get(
                            aurl, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=60),
                            ssl=ssl_ctx
                        ) as resp:
                            if resp.status == 200:
                                with open(audio_path, "wb") as f:
                                    async for chunk in resp.content.iter_chunked(65536):
                                        f.write(chunk)
                                has_audio = True
                                tasks[task_id]["percent"] = 90.0
                                break
                    except Exception:
                        continue

            # 3. Merge with ffmpeg
            if has_audio:
                tasks[task_id]["status"] = "merging"
                tasks[task_id]["percent"] = 95.0
                import subprocess as sp
                cmd = [
                    "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
                    "-c:v", "copy", "-c:a", "aac", "-shortest",
                    "-movflags", "+faststart", out_path
                ]
                loop = asyncio.get_running_loop()
                ret = await loop.run_in_executor(
                    None, lambda: sp.run(cmd, capture_output=True).returncode
                )
                if ret != 0:
                    os.rename(video_path, out_path)
                else:
                    os.remove(video_path)
                    os.remove(audio_path)
            else:
                os.rename(video_path, out_path)

        tasks[task_id]["status"] = "done"
        tasks[task_id]["percent"] = 100.0
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = _tb.format_exc()
        for p in [video_path, audio_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

async def download(
    url: str,
    format_id: str,
    task_id: str,
    video_urls=None,
    audio_urls=None,
    requested_format: Optional[dict] = None,
) -> None:
    import yt_dlp

    url = _normalize_url(url)
    platform = _detect_platform(url)

    # For Douyin, download video + audio separately, then merge with ffmpeg
    if platform == "Douyin":
        try:
            if video_urls:
                await _download_douyin_merged(video_urls, audio_urls, task_id)
            else:
                try:
                    from backend.douyin.api import extract_info as douyin_extract_info
                    info = douyin_extract_info(url)
                    vurls = info.get("_video_urls") if info else []
                    aurls = info.get("_audio_urls") if info else []
                    if vurls:
                        await _download_douyin_merged(vurls, aurls, task_id)
                    else:
                        tasks[task_id] = {"task_id": task_id, "status": "error", "percent": 0.0,
                                          "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": "No direct URL found"}
                except Exception as e:
                    tasks[task_id] = {"task_id": task_id, "status": "error", "percent": 0.0,
                                      "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": str(e)}
        except Exception as e:
            tasks[task_id] = {"task_id": task_id, "status": "error", "percent": 0.0,
                              "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": str(e)}
        return

    if (
        platform != "Douyin"
        and not requested_format
        and "+" not in format_id
        and format_id not in ("best", "bestvideo+bestaudio", "bestvideo+bestaudio/best")
    ):
        try:
            info = extract_info(url)
            for f in info.get("formats", []):
                fid = str(f.get("format_id", ""))
                if fid == format_id:
                    requested_format = f
                    break
        except Exception:
            pass

    tasks[task_id] = {
        "task_id": task_id, "status": "downloading", "percent": 0.0,
        "speed": None, "eta": None, "filename": None, "filesize_str": None, "error": None,
    }

    tmpl = os.path.join(config.DOWNLOAD_DIR, f"%(title).100s [{task_id}-%(id)s-%(format_id)s].%(ext)s")

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            dl = d.get("downloaded_bytes") or 0
            if total > 0:
                tasks[task_id]["percent"] = round(dl / total * 100, 1)
            tasks[task_id]["speed"] = _clean_ansi(d.get("_speed_str", "")).strip()
            tasks[task_id]["eta"] = _clean_ansi(d.get("_eta_str", "")).strip()
            if total:
                tasks[task_id]["filesize_str"] = _format_size(total)
        elif d["status"] == "finished":
            tasks[task_id]["percent"] = 100.0
            fn = d.get("filename", "")
            if fn:
                tasks[task_id]["filename"] = os.path.basename(fn)

    format_candidates = _format_candidates(format_id, requested_format, platform)
    clients = _YOUTUBE_CLIENTS if platform == "YouTube" else [None]

    def _run():
        last_error = ""
        attempt = 0
        for candidate in format_candidates:
            for client in clients:
                attempt += 1
                label = _youtube_strategy_label(client)
                tasks[task_id]["status"] = "downloading"
                if attempt > 1:
                    tasks[task_id]["error"] = f"Retrying YouTube download with {label} / {candidate}"

                extra_opts = {
                    "format": candidate,
                    "outtmpl": tmpl,
                    "progress_hooks": [hook],
                    "writethumbnail": True,
                }
                if platform == "YouTube":
                    extra_opts["http_chunk_size"] = 10 * 1024 * 1024
                if platform == "Douyin":
                    extra_opts["http_headers"] = {**_BROWSER_HEADERS, "Referer": "https://www.douyin.com/"}

                extractor_args = _youtube_extractor_args(client) if platform == "YouTube" else None
                opts = _build_opts(extra=extra_opts, extractor_args=extractor_args)
                started_at = time.time()

                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                    final_file = _newest_media_file(started_at, marker=task_id)
                    if requested_format and not final_file:
                        raise RuntimeError("Selected format did not produce a completed output file")
                    if final_file and not _downloaded_format_matches(final_file, task_id, requested_format):
                        try:
                            final_file.unlink()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"Selected format {requested_format.get('format_id')} was downgraded to {final_file.name}"
                        )
                    if final_file:
                        tasks[task_id]["filename"] = final_file.name
                        tasks[task_id]["filesize_str"] = _format_size(final_file.stat().st_size)
                    tasks[task_id]["status"] = "done"
                    tasks[task_id]["percent"] = 100.0
                    tasks[task_id]["error"] = None
                    return
                except Exception as e:
                    last_error = _clean_ansi(str(e))
                    if _is_drm_error(last_error):
                        tasks[task_id]["status"] = "error"
                        tasks[task_id]["error"] = _format_drm_error(platform)
                        return
                    if platform != "YouTube" or not _is_download_retryable_error(last_error):
                        tasks[task_id]["status"] = "error"
                        tasks[task_id]["error"] = last_error
                        return

        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = _format_youtube_failure(last_error or "Unknown error", requested_format)

    try:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _run)
    except asyncio.CancelledError:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = "Download cancelled"
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = _clean_ansi(str(e))


def get_progress(task_id: str) -> Optional[dict]:
    return tasks.get(task_id)








