"""Startup diagnostics for optional runtime dependencies."""

from __future__ import annotations

import importlib.util
import shutil
from typing import Any, Dict, List


def run_startup_checks() -> Dict[str, Any]:
    required = ["fastapi", "uvicorn", "yt_dlp", "dotenv", "aiohttp", "openai", "requests", "gmssl"]
    optional = ["whisper"]
    missing_required: List[str] = [name for name in required if importlib.util.find_spec(name) is None]
    missing_optional: List[str] = [name for name in optional if importlib.util.find_spec(name) is None]
    ffmpeg_path = shutil.which("ffmpeg")
    return {
        "ok": not missing_required,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "ffmpeg": ffmpeg_path,
        "warnings": ([] if ffmpeg_path else ["ffmpeg not found in PATH; merging, conversion, and Whisper may fail."]),
    }
