"""Subtitle extraction using yt-dlp's built-in subtitle engine.

YouTube-only for v1.  Works both standalone and as a queue job.

Output layout:
    downloads/subtitles/<video_id>/
        <lang>.srt          — raw subtitle file
        <lang>.txt          — plain-text transcript (timestamps only when requested)
        manifest.json       — metadata: languages, line counts, source type
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import config

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _subtitle_dir(video_id: str) -> Path:
    d = Path(config.SUBTITLE_DIR) / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    # fallback: use a hash of the URL
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _parse_srt_to_text(srt_path: str) -> str:
    """Strip SRT timestamps and metadata → plain transcript text."""
    if not os.path.exists(srt_path):
        return ""
    with open(srt_path, encoding="utf-8") as f:
        raw = f.read()

    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def _parse_srt_to_segments(srt_path: str) -> list:
    """Parse an SRT file into a list of timestamped segments.

    Returns: [{ index, start, end, start_sec, text }]
    """
    if not os.path.exists(srt_path):
        return []
    with open(srt_path, encoding="utf-8") as f:
        raw = f.read()

    segments = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        idx = int(lines[0].strip()) if lines[0].strip().isdigit() else 0
        m = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip(),
        )
        if not m:
            continue
        start_sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        end_sec = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000
        text = "\n".join(lines[2:]).strip()
        text = re.sub(r"<[^>]+>", "", text)
        segments.append({
            "index": idx,
            "start": f"{m.group(1)}:{m.group(2)}:{m.group(3)}",
            "end": f"{m.group(5)}:{m.group(6)}:{m.group(7)}",
            "start_sec": round(start_sec, 1),
            "text": text,
        })
    return segments


def _extract_subtitle_info(ydl, url: str, platform: str) -> dict:
    """Extract caption metadata without selecting a media format.

    Some YouTube player responses expose caption tracks but no media formats
    usable by yt-dlp's default ``best`` selector. Subtitle work only needs the
    caption metadata, so processing the media result is both unnecessary and
    a source of ``Requested format is not available`` failures.
    """
    return ydl.extract_info(url, download=False, process=platform != "YouTube")


def _select_subtitle_track(tracks: list) -> Optional[dict]:
    """Choose a text-friendly subtitle representation from one language."""
    if not tracks:
        return None
    extension_priority = {
        "vtt": 0,
        "srt": 1,
        "srv3": 2,
        "srv2": 3,
        "srv1": 4,
        "ttml": 5,
        "json3": 6,
    }
    candidates = [track for track in tracks if track.get("url")]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda track: extension_priority.get(str(track.get("ext") or "").lower(), 99),
    )


def _download_youtube_subtitle_tracks(ydl, info: dict, out_dir: str, languages: List[str]) -> List[str]:
    """Download YouTube caption URLs directly, without downloading media."""
    manual_subs = info.get("subtitles") or {}
    automatic_subs = info.get("automatic_captions") or {}
    downloaded = []
    video_id = str(info.get("id") or "subtitle")

    for language in languages:
        # Manual captions take precedence, matching the metadata returned to
        # the client. Auto captions are used when manual captions are absent.
        track = _select_subtitle_track(manual_subs.get(language) or automatic_subs.get(language) or [])
        if not track:
            continue

        extension = re.sub(r"[^a-z0-9]", "", str(track.get("ext") or "vtt").lower()) or "vtt"
        safe_language = re.sub(r"[^A-Za-z0-9_-]", "_", language)
        target = Path(out_dir) / f"{video_id}.{safe_language}.{extension}"
        response = ydl.urlopen(track["url"])
        try:
            target.write_bytes(response.read())
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
        downloaded.append(language)

    return downloaded


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

async def extract_subtitles(
    url: str,
    task_id: str = "",
    languages: Optional[List[str]] = None,
) -> dict:
    """Download subtitles for a YouTube video.

    Args:
        url: YouTube video URL.
        task_id: Task id for progress reporting (optional).
        languages: List of language codes (e.g. ["en", "zh-Hans"]).
                   None / empty = auto (English / first available).

    Returns dict:
        { video_id, title, available_langs: [...], extracted: [
            { lang, lang_name, source: "manual"|"auto", text: str, srt_path, txt_path, line_count }
        ] }
    """
    if not languages:
        languages = ["en"]

    video_id = _extract_video_id(url)
    out_dir = _subtitle_dir(video_id)

    # Run yt-dlp in a thread — it's blocking
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _extract_subtitles_sync, url, video_id, str(out_dir), languages, task_id
    )


def _extract_subtitles_sync(
    url: str, video_id: str, out_dir: str, languages: List[str], task_id: str
) -> dict:
    import yt_dlp
    from backend.downloader import (
        _YOUTUBE_CLIENTS,
        _clean_ansi,
        _detect_platform,
        _format_drm_error,
        _is_download_retryable_error,
        _is_drm_error,
    )

    platform = _detect_platform(url)
    clients = _YOUTUBE_CLIENTS if platform == "YouTube" else [None]

    # Step 1: fetch info + available subtitle list
    info = None
    last_error = ""
    for client in clients:
        try:
            info_opts = _build_subtitle_opts(out_dir=None, download=False, url=url, client=client)
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = _extract_subtitle_info(ydl, url, platform)
            break
        except Exception as e:
            last_error = _clean_ansi(str(e))
            if _is_drm_error(last_error):
                raise RuntimeError(_format_drm_error(platform))
            if platform != "YouTube" or not _is_download_retryable_error(last_error):
                raise
    if not info:
        raise RuntimeError(_format_subtitle_failure(platform, last_error))

    title = info.get("title", "Unknown")
    available_subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}

    # Merge: manual sub keys + auto sub keys (dedup, prefer manual)
    all_lang_keys: List[str] = list(available_subs.keys()) + [
        k for k in auto_subs if k not in available_subs
    ]
    available_langs = []
    for k in all_lang_keys:
        source = "manual" if k in available_subs else "auto"
        available_langs.append({"code": k, "source": source})

    # Step 2: determine which languages to download
    # If user requested "auto" or the lang only exists as auto, use auto sub
    langs_to_download = []
    for lang in languages:
        if lang in available_subs:
            langs_to_download.append(lang)
        elif lang in auto_subs:
            langs_to_download.append(lang)
        else:
            # Try case-insensitive match
            for k in all_lang_keys:
                if k.lower() == lang.lower():
                    langs_to_download.append(k)
                    break

    if not langs_to_download:
        # If nothing matched, download the first available
        if available_subs:
            langs_to_download = [list(available_subs.keys())[0]]
        elif auto_subs:
            langs_to_download = [list(auto_subs.keys())[0]]

    # Step 3: download selected subtitle files. YouTube captions are fetched
    # from their signed caption URLs directly, so yt-dlp never selects media.
    downloaded = False
    for client in clients:
        try:
            if platform == "YouTube":
                info_opts = _build_subtitle_opts(out_dir=None, download=False, url=url, client=client)
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    client_info = _extract_subtitle_info(ydl, url, platform)
                    downloaded = bool(
                        _download_youtube_subtitle_tracks(ydl, client_info, out_dir, langs_to_download)
                    )
                if not downloaded:
                    last_error = "No requested subtitle tracks are available"
                    continue
            else:
                dl_opts = _build_subtitle_opts(
                    out_dir=out_dir,
                    download=True,
                    languages=langs_to_download,
                    url=url,
                    client=client,
                )
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    ydl.download([url])
                downloaded = True
            break
        except Exception as e:
            last_error = _clean_ansi(str(e))
            if _is_drm_error(last_error):
                raise RuntimeError(_format_drm_error(platform))
            if platform != "YouTube" or not _is_download_retryable_error(last_error):
                raise
            continue
    if not downloaded:
        raise RuntimeError(_format_subtitle_failure(platform, last_error))

    # Step 4: parse downloaded files → text + metadata
    extracted = []
    for lang in langs_to_download:
        source = "manual" if lang in available_subs else "auto"
        srt_candidates = list(Path(out_dir).glob(f"*.{lang}.*")) + list(Path(out_dir).glob(f"*{lang}*.*"))

        srt_path = None
        for p in srt_candidates:
            if p.suffix in (".srt", ".vtt", ".ass"):
                srt_path = str(p)
                break

        if not srt_path:
            continue

        text = _parse_srt_to_text(srt_path)
        segments = _parse_srt_to_segments(srt_path)
        txt_path = str(Path(out_dir) / f"{lang}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        extracted.append({
            "lang": lang,
            "source": source,
            "text": text,
            "text_preview": text[:500] + ("..." if len(text) > 500 else ""),
            "srt_path": srt_path,
            "txt_path": txt_path,
            "line_count": len(text.splitlines()),
            "segment_count": len(segments),
            "segments": segments,
        })

    # Step 5: write manifest
    manifest = {
        "video_id": video_id,
        "title": title,
        "url": url,
        "available_langs": available_langs,
        "extracted": [e["lang"] for e in extracted],
        "out_dir": out_dir,
    }
    manifest_path = Path(out_dir) / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return {
        "video_id": video_id,
        "title": title,
        "available_langs": available_langs,
        "extracted": extracted,
        "out_dir": out_dir,
    }


def _format_subtitle_failure(platform: str, last_error: str) -> str:
    if platform == "YouTube":
        return (
            "YouTube subtitle download failed after trying multiple clients. "
            f"Last error: {last_error or 'Unknown error'}. "
            "Try syncing fresh browser cookies, updating yt-dlp, or retrying later."
        )
    return f"{platform} subtitle download failed: {last_error or 'Unknown error'}"


# ---------------------------------------------------------------------------
# yt-dlp option builders
# ---------------------------------------------------------------------------

def _build_subtitle_opts(
    out_dir: Optional[str] = None,
    download: bool = False,
    languages: Optional[List[str]] = None,
    url: Optional[str] = None,
    client: Optional[str] = None,
) -> dict:
    """Build yt-dlp options for subtitle extraction."""
    from backend.cookies import apply_cookie_options
    from backend.downloader import _BROWSER_HEADERS, _detect_platform, _youtube_extractor_args

    platform = _detect_platform(url or "")
    referer = "https://www.youtube.com/" if platform == "YouTube" else "https://www.bilibili.com/"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "no_playlist": True,
        "extract_flat": False,
        "skip_download": True,
        "socket_timeout": 60,
        "retries": 20,
        "fragment_retries": 20,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "http_headers": {**_BROWSER_HEADERS, "Referer": referer},
        "logger": __import__("logging").getLogger("yt_dlp"),
    }
    if platform == "YouTube":
        extractor_args = _youtube_extractor_args(client)
        if extractor_args:
            opts["extractor_args"] = extractor_args

    # Cookie support — same logic as downloader
    apply_cookie_options(opts, url=url)

    if not download:
        opts["writesubtitles"] = False
        opts["writeautomaticsub"] = False
        return opts

    # Download mode
    if out_dir:
        opts["outtmpl"] = os.path.join(out_dir, "%(id)s.%(ext)s")
        opts["paths"] = {"home": out_dir}

    opts["writesubtitles"] = True
    opts["writeautomaticsub"] = True
    opts["subtitlesformat"] = "srt/vtt/ass"
    opts["convertsubtitles"] = "srt"

    if languages:
        opts["subtitleslangs"] = languages

    return opts
