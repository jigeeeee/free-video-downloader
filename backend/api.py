"""FastAPI application — Video Downloader API."""

import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
from backend.models import (
    URLRequest, VideoInfo, DownloadRequest, DownloadTask,
    FileInfo, FileListResponse,
    SubtitleRequest, SubtitleResult, SubtitleTask,
    SummaryRequest, SummaryResult, SummaryTask,
    MindmapRequest, MindmapResult, MindmapTask,
    AskRequest, AskResponse, AskTask,
    TranscribeTask, BatchRequest, BatchTaskInfo, BatchResponse,
    TranslateRequest, TranslateResponse,
)
from backend.downloader import extract_info, download, get_progress
from backend.subtitle import extract_subtitles as _extract_subtitles
from backend.queue import get_queue, TaskStatus
from backend.ai import summarize_video as _ai_summarize
from backend.ai import generate_mindmap as _ai_mindmap
from backend.ai import ask_video as _ai_ask
from backend.ai import translate_subtitles as _ai_translate
from backend.transcribe import transcribe_file as _whisper_transcribe

# Cache recent parse results to avoid duplicate API calls (Douyin rate-limits)
_info_cache = {}


app = FastAPI(
    title="Universal Video Downloader API",
    description="Video download service powered by yt-dlp",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "video-downloader"}


@app.post("/api/info", response_model=VideoInfo)
async def get_video_info(req: URLRequest):
    try:
        info = await asyncio.to_thread(extract_info, req.url)
        return VideoInfo(**info)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download", response_model=DownloadTask)
async def start_download(req: DownloadRequest):
    
    # Try cache first, then parse
    cache_key = req.url.strip()
    info = _info_cache.get(cache_key)
    if info is None:
        try:
            info = await asyncio.to_thread(extract_info, req.url)
            _info_cache[cache_key] = info
        except Exception:
            info = {}
    video_urls = info.get("_video_urls") if info else None
    audio_urls = info.get("_audio_urls") if info else None
    # ── Submit via task queue ──
    queue = await get_queue()
    task_id = await queue.enqueue(
        "download",
        _run_download_job,
        url=req.url, format_id=req.format_id,
        video_urls=video_urls, audio_urls=audio_urls,
    )
    return DownloadTask(task_id=task_id, status="queued")


@app.get("/api/progress/{task_id}", response_model=DownloadTask)
async def get_download_progress(task_id: str):
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        # fallback: check legacy downloader.tasks dict
        progress = get_progress(task_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Task not found")
        return DownloadTask(**progress)
    return DownloadTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        error=record.error,
        filename=(record.result or {}).get("filename"),
        filesize_str=(record.result or {}).get("filesize_str"),
    )


@app.get("/api/files", response_model=FileListResponse)
async def list_files():
    download_dir = Path(config.DOWNLOAD_DIR)
    files = []
    if download_dir.exists():
        for f in sorted(download_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and not f.name.startswith("."):
                size = f.stat().st_size
                if size >= 1_000_000_000: size_str = f"{size/1_000_000_000:.1f} GB"
                elif size >= 1_000_000: size_str = f"{size/1_000_000:.1f} MB"
                elif size >= 1_000: size_str = f"{size/1_000:.1f} KB"
                else: size_str = f"{size} B"
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                files.append(FileInfo(name=f.name, size=size, size_str=size_str, date=mtime.isoformat()))
    return FileListResponse(files=files)


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    filepath = Path(config.DOWNLOAD_DIR) / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{filename}")
async def serve_file(filename: str):
    filepath = Path(config.DOWNLOAD_DIR) / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(filepath), filename=filename, media_type="application/octet-stream")


# ── Task-queue job wrappers ──────────────────────────────────────────────

async def _run_download_job(task_id: str, **kwargs) -> dict:
    """Bridge: queue.JobFunc → legacy downloader.download().

    The queue calls job(task_id, **kwargs).  We forward to the existing
    download() which writes progress into downloader.tasks[task_id].
    """
    await download(
        url=kwargs["url"],
        format_id=kwargs["format_id"],
        task_id=task_id,
        video_urls=kwargs.get("video_urls"),
        audio_urls=kwargs.get("audio_urls"),
    )
    progress = get_progress(task_id) or {}
    return {
        "filename": progress.get("filename"),
        "filesize_str": progress.get("filesize_str"),
        "status": progress.get("status", "done"),
    }


# ── Subtitle endpoints ───────────────────────────────────────────────────

@app.post("/api/subtitles", response_model=SubtitleTask)
async def start_subtitle_extraction(req: SubtitleRequest):
    """Submit a subtitle-extraction job.  Returns immediately with task_id."""
    queue = await get_queue()
    task_id = await queue.enqueue(
        "subtitle",
        _run_subtitle_job,
        url=req.url,
        languages=req.languages,
    )
    return SubtitleTask(task_id=task_id, status="queued")


@app.get("/api/subtitles/{task_id}", response_model=SubtitleTask)
async def get_subtitle_status(task_id: str):
    """Poll subtitle-extraction progress / result."""
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    result = None
    if record.result:
        try:
            result = SubtitleResult(**record.result)
        except Exception:
            result = None

    return SubtitleTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=result,
        error=record.error,
    )


async def _run_subtitle_job(task_id: str, **kwargs) -> dict:
    """Bridge: queue.JobFunc → subtitle.extract_subtitles()."""
    languages = kwargs.get("languages")
    return await _extract_subtitles(
        url=kwargs["url"],
        task_id=task_id,
        languages=languages,
    )


# ── AI Summary endpoint (combines subtitle extraction + AI summarization) ─

@app.post("/api/summary", response_model=SummaryTask)
async def start_summary(req: SummaryRequest):
    """Submit a video summary job. Internally: extract subtitles → AI summarize."""
    queue = await get_queue()
    task_id = await queue.enqueue(
        "summary",
        _run_summary_job,
        url=req.url,
        lang=req.lang,
    )
    return SummaryTask(task_id=task_id, status="queued")


@app.get("/api/summary/{task_id}", response_model=SummaryTask)
async def get_summary_status(task_id: str):
    """Poll summary progress / result."""
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    result = None
    if record.result:
        try:
            result = SummaryResult(**record.result)
        except Exception:
            result = None

    return SummaryTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=result,
        error=record.error,
    )


async def _run_summary_job(task_id: str, **kwargs) -> dict:
    """Full pipeline: extract subtitles → AI summarize.

    This is a queue JobFunc — called by the task queue.
    """
    url = kwargs["url"]
    lang = kwargs.get("lang", "zh")

    # Step 1: extract subtitles
    subtitle_result = await _extract_subtitles(
        url=url, task_id=task_id, languages=["en"]
    )

    # Combine all extracted subtitle texts
    all_text = ""
    for entry in subtitle_result.get("extracted", []):
        all_text += entry.get("text", "") + "\n\n"

    if not all_text.strip():
        return {
            "error": "No subtitle text extracted. The video may not have subtitles.",
            "one_liner": "", "chapters": [], "key_points": [], "tags": [],
            "video_title": subtitle_result.get("title", ""),
        }

    title = subtitle_result.get("title", "Unknown")

    # Step 2: AI summarize
    summary = await _ai_summarize(
        title=title,
        subtitle_text=all_text.strip(),
        lang=lang,
    )

    summary["video_title"] = title
    return summary


# ── Mindmap endpoint ─────────────────────────────────────────────────────

@app.post("/api/mindmap", response_model=MindmapTask)
async def start_mindmap(req: MindmapRequest):
    """Submit a mindmap generation job. Internally: extract subtitles → generate Mermaid mindmap."""
    queue = await get_queue()
    task_id = await queue.enqueue(
        "mindmap",
        _run_mindmap_job,
        url=req.url,
        lang=req.lang,
    )
    return MindmapTask(task_id=task_id, status="queued")


@app.get("/api/mindmap/{task_id}", response_model=MindmapTask)
async def get_mindmap_status(task_id: str):
    """Poll mindmap progress / result."""
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    result = None
    if record.result:
        try:
            result = MindmapResult(**record.result)
        except Exception:
            result = None

    return MindmapTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=result,
        error=record.error,
    )


async def _run_mindmap_job(task_id: str, **kwargs) -> dict:
    """Full pipeline: extract subtitles → AI mindmap generation."""
    url = kwargs["url"]
    lang = kwargs.get("lang", "zh")

    subtitle_result = await _extract_subtitles(
        url=url, task_id=task_id, languages=["en"]
    )

    all_text = ""
    for entry in subtitle_result.get("extracted", []):
        all_text += entry.get("text", "") + "\n\n"

    if not all_text.strip():
        return {
            "mermaid": "# No subtitles available",
            "video_title": subtitle_result.get("title", "Unknown"),
            "error": "No subtitle text extracted",
        }

    title = subtitle_result.get("title", "Unknown")
    result = await _ai_mindmap(
        title=title,
        subtitle_text=all_text.strip(),
        lang=lang,
    )
    return result


# ── AI Q&A endpoint ──────────────────────────────────────────────────────

@app.post("/api/ask", response_model=AskTask)
async def start_ask(req: AskRequest):
    """Submit a video Q&A question. Internally: extract subtitles → AI answer."""
    queue = await get_queue()
    task_id = await queue.enqueue(
        "ask",
        _run_ask_job,
        url=req.url,
        question=req.question,
        lang=req.lang,
        history=req.history,
    )
    return AskTask(task_id=task_id, status="queued")


@app.get("/api/ask/{task_id}", response_model=AskTask)
async def get_ask_status(task_id: str):
    """Poll Q&A progress / result."""
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    result = None
    if record.result:
        try:
            result = AskResponse(**record.result)
        except Exception:
            result = None

    return AskTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=result,
        error=record.error,
    )


async def _run_ask_job(task_id: str, **kwargs) -> dict:
    """Full pipeline: extract subtitles → AI Q&A."""
    url = kwargs["url"]
    question = kwargs["question"]
    lang = kwargs.get("lang", "zh")
    history = kwargs.get("history", [])

    # Convert ChatTurn models → dicts
    history_dicts = [{"question": h.question, "answer": h.answer} for h in history] if history else None

    subtitle_result = await _extract_subtitles(
        url=url, task_id=task_id, languages=["en"]
    )

    all_text = ""
    for entry in subtitle_result.get("extracted", []):
        all_text += entry.get("text", "") + "\n\n"

    if not all_text.strip():
        return {
            "question": question,
            "answer": "No subtitle text available for this video.",
            "video_title": subtitle_result.get("title", "Unknown"),
        }

    title = subtitle_result.get("title", "Unknown")
    result = await _ai_ask(
        title=title,
        subtitle_text=all_text.strip(),
        question=question,
        chat_history=history_dicts,
        lang=lang,
    )
    result["video_title"] = title
    return result


# ── Transcribe (local file upload + Whisper) ─────────────────────────────

@app.post("/api/transcribe", response_model=TranscribeTask)
async def start_transcribe(file: UploadFile = FastAPIFile(...), language: Optional[str] = None):
    """Upload a local audio/video file for Whisper transcription."""
    # Save uploaded file to temp location
    upload_dir = Path(config.DOWNLOAD_DIR) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"upload_{os.urandom(4).hex()}_{file.filename or 'unknown'}"
    file_path = upload_dir / safe_name
    content = await file.read()
    file_path.write_bytes(content)

    queue = await get_queue()
    task_id = await queue.enqueue(
        "transcribe",
        _run_transcribe_job,
        file_path=str(file_path),
        language=language,
    )
    return TranscribeTask(task_id=task_id, status="queued")


@app.get("/api/transcribe/{task_id}", response_model=TranscribeTask)
async def get_transcribe_status(task_id: str):
    """Poll transcription progress / result."""
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")

    return TranscribeTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=record.result,
        error=record.error,
    )


async def _run_transcribe_job(task_id: str, **kwargs) -> dict:
    """Whisper transcription job."""
    return await _whisper_transcribe(
        file_path=kwargs["file_path"],
        task_id=task_id,
        language=kwargs.get("language"),
    )


# ── Batch queue (multiple URLs at once) ──────────────────────────────────

# In-memory batch tracker (same lifetime as the in-memory queue)
_batches = {}


@app.post("/api/batch", response_model=BatchResponse)
async def submit_batch(req: BatchRequest):
    """Submit multiple URLs for parallel processing.

    Each URL gets its own download task. All tracked under one batch_id.
    """
    queue = await get_queue()
    batch_id = os.urandom(4).hex()
    tasks = []

    for url in req.urls:
        task_id = await queue.enqueue(
            "download",
            _run_download_job,
            url=url,
            format_id="bestvideo+bestaudio/best",
            video_urls=None,
            audio_urls=None,
        )
        tasks.append(BatchTaskInfo(task_id=task_id, url=url, task_type="download", status="queued"))

    _batches[batch_id] = {
        "batch_id": batch_id,
        "urls": req.urls,
        "task_ids": [t.task_id for t in tasks],
    }

    return BatchResponse(
        batch_id=batch_id,
        tasks=tasks,
        total=len(tasks),
        queued=len(tasks),
    )


@app.get("/api/batch/{batch_id}", response_model=BatchResponse)
async def get_batch_status(batch_id: str):
    """Check the status of all tasks in a batch."""
    batch = _batches.get(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    queue = await get_queue()
    tasks = []
    counts = {"done": 0, "processing": 0, "queued": 0, "error": 0}

    for i, tid in enumerate(batch["task_ids"]):
        record = queue.get(tid)
        status = record.status.value if record else "unknown"
        tasks.append(BatchTaskInfo(
            task_id=tid,
            url=batch["urls"][i] if i < len(batch["urls"]) else "",
            task_type="download",
            status=status,
        ))
        if status in counts:
            counts[status] += 1

    return BatchResponse(
        batch_id=batch_id,
        tasks=tasks,
        total=len(tasks),
        done=counts["done"],
        processing=counts["processing"],
        queued=counts["queued"],
        error=counts["error"],
    )


# ── Subtitle translation ─────────────────────────────────────────────────

@app.post("/api/translate", response_model=TranslateResponse)
async def translate_text(req: TranslateRequest):
    """Translate subtitle text to the target language (via DeepSeek)."""
    result = await _ai_translate(
        subtitle_text=req.text,
        target_lang=req.target_lang,
    )
    return TranslateResponse(**result)
