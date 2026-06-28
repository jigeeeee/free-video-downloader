"""Local audio/video transcription using OpenAI Whisper (subprocess).

Runs whisper in a subprocess via ThreadPoolExecutor to avoid asyncio
subprocess issues on Windows.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SCRIPT = (Path(__file__).parent / "_whisper_worker.py").resolve()


async def transcribe_file(
    file_path: str,
    task_id: str = "",
    language: Optional[str] = None,
    model_name: Optional[str] = None,
) -> dict:
    """Transcribe an audio/video file with Whisper (via subprocess).

    Args:
        file_path: Path to the media file.
        language: Optional language hint (e.g. "en", "zh").
        model_name: Whisper model ("tiny" / "base" / "small" / "medium" / "large").

    Returns:
        { text, segments: [{start, end, text}], language, duration, model }
    """
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _transcribe_subprocess,
        file_path,
        language or "",
        model_name or "base",
    )


def _transcribe_subprocess(
    file_path: str, language: str, model_name: str
) -> dict:
    cmd = [
        sys.executable, str(_SCRIPT),
        "--file", str(file_path),
        "--model", model_name,
    ]
    if language:
        cmd += ["--language", language]

    env = {**os.environ, "TQDM_DISABLE": "1", "PYTHONIOENCODING": "utf-8"}
    project_root = str(Path(__file__).resolve().parent.parent)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        cwd=project_root,
        env=env,
        timeout=600,
    )

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Whisper failed (code {proc.returncode}): {err[:500]}")

    result = json.loads(proc.stdout.decode("utf-8"))
    return result
