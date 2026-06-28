"""Subtitle extraction using yt-dlp's built-in subtitle engine.

YouTube-only for v1.  Works both standalone and as a queue job.

Output layout:
    downloads/subtitles/<video_id>/
        <lang>.srt          — raw subtitle file
        <lang>.txt          — plain-text transcript (timestamps only when requested)
        manifest.json       — metadata: languages, line counts, source type
"""

from __future__ import annotations

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
    import asyncio
    from backend.queue import get_queue

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

    # Step 1: fetch info + available subtitle list
    info_opts = _build_subtitle_opts(out_dir=None, download=False)
    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)

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

    # Step 3: download selected subtitle files
    dl_opts = _build_subtitle_opts(
        out_dir=out_dir,
        download=True,
        languages=langs_to_download,
    )
    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        ydl.download([url])

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


# ---------------------------------------------------------------------------
# yt-dlp option builders
# ---------------------------------------------------------------------------

def _build_subtitle_opts(
    out_dir: Optional[str] = None,
    download: bool = False,
    languages: Optional[List[str]] = None,
) -> dict:
    """Build yt-dlp options for subtitle extraction.

    When download=False: just fetch metadata (info stage).
    When download=True:  actually download and convert subtitle files.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "no_playlist": True,
        "extract_flat": False,
        "skip_download": True,           # Never download the video itself
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        },
        "logger": __import__("logging").getLogger("yt_dlp"),
    }

    if not download:
        # Info-only: don't write anything, just return metadata
        opts["writesubtitles"] = False
        opts["writeautomaticsub"] = False
        return opts

    # Download mode
    if out_dir:
        opts["outtmpl"] = os.path.join(out_dir, "%(id)s.%(ext)s")
        opts["paths"] = {"home": out_dir}

    opts["writesubtitles"] = True
    opts["writeautomaticsub"] = True     # auto-generated captions
    opts["subtitlesformat"] = "srt/vtt/ass"  # prefer srt
    opts["convertsubtitles"] = "srt"     # convert everything to srt

    if languages:
        opts["subtitleslangs"] = languages

    # Cookie support (same logic as downloader.py)
    from backend.downloader import _get_cookiefile
    cf = _get_cookiefile()
    if cf:
        opts["cookiefile"] = cf

    return opts
