"""Local media conversion helpers powered by ffmpeg."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import config

_SAFE_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".mp3", ".m4a", ".wav"}


def safe_filename(name: str, fallback: str = "media") -> str:
    base = os.path.basename(name or fallback)
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    return base or fallback


def resolve_download_file(filename: str) -> Path:
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError("Invalid file path")
    safe_name = safe_filename(filename)
    root = Path(config.DOWNLOAD_DIR).resolve()
    path = (root / safe_name).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Invalid file path")
    return path


async def convert_media(
    task_id: str,
    filename: str,
    target_format: str,
    mode: str = "convert",
    bitrate: Optional[str] = None,
) -> dict:
    source = resolve_download_file(filename)
    if not source.exists() or source.suffix.lower() not in _SAFE_EXTENSIONS:
        raise FileNotFoundError("Source media not found")

    fmt = target_format.lower().lstrip(".")
    if fmt not in {"mp4", "mkv", "webm", "mp3", "m4a", "wav"}:
        raise ValueError("Unsupported target format")

    out_name = safe_filename(f"{source.stem}_{mode}_{task_id}.{fmt}")
    output = resolve_download_file(out_name)
    cmd = ["ffmpeg", "-y", "-i", str(source)]
    if mode == "audio" or fmt in {"mp3", "m4a", "wav"}:
        cmd += ["-vn"]
        if bitrate:
            cmd += ["-b:a", bitrate]
    elif mode == "compress":
        cmd += ["-vcodec", "libx264", "-crf", "28", "-preset", "veryfast", "-acodec", "aac"]
    else:
        cmd += ["-c:v", "copy", "-c:a", "aac"]
    cmd.append(str(output))

    loop = asyncio.get_running_loop()
    proc = await loop.run_in_executor(None, lambda: subprocess.run(cmd, capture_output=True, text=True))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffmpeg conversion failed")[-1000:])

    size = output.stat().st_size
    return {
        "filename": output.name,
        "source": source.name,
        "target_format": fmt,
        "size": size,
        "filesize_str": _format_size(size),
    }


def _format_size(size: int) -> str:
    if size >= 1_000_000_000:
        return f"{size/1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size/1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size/1_000:.1f} KB"
    return f"{size} B"
