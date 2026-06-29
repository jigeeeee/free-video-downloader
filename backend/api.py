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
from backend import storage
from backend.models import (
    URLRequest, VideoInfo, DownloadRequest, DownloadTask,
    FileInfo, FileListResponse,
    SubtitleRequest, SubtitleResult, SubtitleTask,
    SummaryRequest, SummaryResult, SummaryTask,
    MindmapRequest, MindmapResult, MindmapTask,
    AskRequest, AskResponse, AskTask,
    TranscribeTask, BatchRequest, BatchTaskInfo, BatchResponse,
    TranslateRequest, TranslateResponse,
    TaskRecordResponse, TaskListResponse, HistoryResponse,
    ConvertRequest, ConvertTask, RewriteRequest, RewriteTask,
)
from backend.downloader import extract_info, download, get_progress
from backend.subtitle import extract_subtitles as _extract_subtitles
from backend.queue import get_queue, TaskStatus
from backend.ai import summarize_video as _ai_summarize
from backend.ai import generate_mindmap as _ai_mindmap
from backend.ai import ask_video as _ai_ask
from backend.ai import translate_subtitles as _ai_translate
from backend.ai import rewrite_content as _ai_rewrite
from backend.transcribe import transcribe_file as _whisper_transcribe
from backend.cookies import write_synced_cookiefile
from backend.media import convert_media as _convert_media
from backend.media import resolve_download_file, safe_filename
from backend.startup_checks import run_startup_checks
from backend.bilibili_auth import (
    generate_qrcode as _bili_gen_qr,
    poll_qrcode as _bili_poll_qr,
    get_saved_cookie_path as _bili_cookie,
    refresh_cookies as _bili_refresh,
)

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


@app.on_event("startup")
async def startup():
    await _run_on_startup()


@app.get("/api/health")
async def health():
    checks = run_startup_checks()
    return {"status": "ok" if checks["ok"] else "degraded", "service": "video-downloader", "checks": checks}


@app.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(limit: int = 100):
    queue = await get_queue()
    records = sorted(queue.list().values(), key=lambda r: r.created_at or "", reverse=True)[:limit]
    return TaskListResponse(tasks=[_task_record_response(r) for r in records])


@app.get("/api/tasks/{task_id}", response_model=TaskRecordResponse)
async def get_task(task_id: str):
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    _sync_legacy_progress(record)
    return _task_record_response(record)


@app.post("/api/tasks/{task_id}/retry", response_model=TaskRecordResponse)
async def retry_task(task_id: str):
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    if record.status.value != "error":
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")
    job = _job_for_task(record.task_type)
    if not job:
        raise HTTPException(status_code=400, detail=f"Retry is not supported for task type: {record.task_type}")
    new_id = await queue.enqueue(record.task_type, job, **(record.metadata or {}))
    new_record = queue.get(new_id)
    return _task_record_response(new_record)


@app.get("/api/history", response_model=HistoryResponse)
async def history(limit: int = 100):
    return HistoryResponse(**storage.list_history(limit=limit))


@app.post("/api/info", response_model=VideoInfo)
async def get_video_info(req: URLRequest):
    try:
        info = await asyncio.to_thread(extract_info, req.url)
        _cache_video_info(req.url, info)
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
            _cache_video_info(req.url, info)
        except Exception:
            info = {}
    video_urls = info.get("_video_urls") if info else None
    audio_urls = info.get("_audio_urls") if info else None
    requested_format = _find_requested_format(info, req.format_id) if info else None
    # ── Submit via task queue ──
    queue = await get_queue()
    task_id = await queue.enqueue(
        "download",
        _run_download_job,
        url=req.url, format_id=req.format_id,
        video_urls=video_urls, audio_urls=audio_urls,
        requested_format=requested_format,
    )
    return DownloadTask(task_id=task_id, status="queued")


@app.get("/api/progress/{task_id}", response_model=DownloadTask)
async def get_download_progress(task_id: str):
    # Check legacy downloader.tasks first — has real-time percent/speed/eta
    progress = get_progress(task_id)
    if progress:
        _persist_progress(task_id, progress)
        return DownloadTask(**progress)
    # Fallback: check queue record
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
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
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov"):
                size = f.stat().st_size
                if size >= 1_000_000_000: size_str = f"{size/1_000_000_000:.1f} GB"
                elif size >= 1_000_000: size_str = f"{size/1_000_000:.1f} MB"
                elif size >= 1_000: size_str = f"{size/1_000:.1f} KB"
                else: size_str = f"{size} B"
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                # Check for thumbnail
                thumb = None
                for ext in (".jpg", ".png", ".webp"):
                    tn = f.with_suffix(ext)
                    if tn.exists():
                        thumb = f"/api/download/{tn.name}"
                        break
                storage.save_file(f.name, size, size_str, str(f), thumb)
                files.append(FileInfo(name=f.name, size=size, size_str=size_str, date=mtime.isoformat(), thumbnail=thumb))
    return FileListResponse(files=files)


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    try:
        filepath = resolve_download_file(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{filename}")
async def serve_file(filename: str):
    try:
        filepath = resolve_download_file(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")
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
        requested_format=kwargs.get("requested_format"),
    )
    progress = get_progress(task_id) or {}
    if progress.get("status") == "error":
        raise RuntimeError(progress.get("error") or "Download failed")
    if progress.get("filename"):
        _save_download_file(progress.get("filename"))
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
    storage.save_ai_result(task_id, "summary", summary, title=title, url=url)
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
    storage.save_ai_result(task_id, "mindmap", result, title=title, url=url)
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
    storage.save_ai_result(task_id, "ask", result, title=title, url=url)
    return result


# ── Transcribe (local file upload + Whisper) ─────────────────────────────

@app.post("/api/transcribe", response_model=TranscribeTask)
async def start_transcribe(file: UploadFile = FastAPIFile(...), language: Optional[str] = None):
    """Upload a local audio/video file for Whisper transcription."""
    allowed_suffixes = {".mp3", ".mp4", ".wav", ".m4a", ".webm", ".mkv", ".mov"}
    original_name = safe_filename(file.filename or "upload")
    if Path(original_name).suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Unsupported upload type")
    # Save uploaded file to temp location
    upload_dir = Path(config.DOWNLOAD_DIR) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"upload_{os.urandom(4).hex()}_{original_name}"
    file_path = upload_dir / safe_name
    content = await file.read()
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {config.MAX_UPLOAD_MB} MB limit")
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


# ── Convert local media with ffmpeg ──────────────────────────────────────

@app.post("/api/convert", response_model=ConvertTask)
async def start_convert(req: ConvertRequest):
    queue = await get_queue()
    task_id = await queue.enqueue(
        "convert",
        _run_convert_job,
        filename=req.filename,
        target_format=req.target_format,
        mode=req.mode,
        bitrate=req.bitrate,
    )
    return ConvertTask(task_id=task_id, status="queued")


@app.get("/api/convert/{task_id}", response_model=ConvertTask)
async def get_convert_status(task_id: str):
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return ConvertTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=record.result,
        error=record.error,
    )


async def _run_convert_job(task_id: str, **kwargs) -> dict:
    result = await _convert_media(
        task_id=task_id,
        filename=kwargs["filename"],
        target_format=kwargs.get("target_format", "mp3"),
        mode=kwargs.get("mode", "audio"),
        bitrate=kwargs.get("bitrate"),
    )
    _save_download_file(result["filename"])
    return result


# ── AI content rewriting ─────────────────────────────────────────────────

@app.post("/api/rewrite", response_model=RewriteTask)
async def start_rewrite(req: RewriteRequest):
    queue = await get_queue()
    task_id = await queue.enqueue(
        "rewrite",
        _run_rewrite_job,
        url=req.url,
        title=req.title,
        text=req.text,
        style=req.style,
        lang=req.lang,
    )
    return RewriteTask(task_id=task_id, status="queued")


@app.get("/api/rewrite/{task_id}", response_model=RewriteTask)
async def get_rewrite_status(task_id: str):
    queue = await get_queue()
    record = queue.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return RewriteTask(
        task_id=record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=record.result,
        error=record.error,
    )


async def _run_rewrite_job(task_id: str, **kwargs) -> dict:
    title = kwargs.get("title") or "Untitled"
    source_text = kwargs.get("text") or ""
    url = kwargs.get("url") or ""
    if not source_text and url:
        subtitle_result = await _extract_subtitles(url=url, task_id=task_id, languages=["zh-Hans", "zh", "zh-CN", "en"])
        title = title or subtitle_result.get("title", "Untitled")
        source_text = "\n\n".join(entry.get("text", "") for entry in subtitle_result.get("extracted", []))
    if not source_text.strip():
        raise RuntimeError("No source text available for rewriting")
    result = await _ai_rewrite(
        title=title,
        source_text=source_text.strip(),
        style=kwargs.get("style", "notes"),
        lang=kwargs.get("lang", "zh"),
    )
    storage.save_ai_result(task_id, "rewrite", result, title=title, url=url)
    return result


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


# ── Bilibili QR Login ────────────────────────────────────────────────────

@app.post("/api/bilibili/qrcode")
@app.get("/api/bilibili/qrcode")
async def bilibili_qrcode():
    """Generate a Bilibili login QR code. Returns { url, qrcode_key }."""
    return await _bili_gen_qr()


@app.get("/api/bilibili/qrcode/status")
async def bilibili_qrcode_status(qrcode_key: str):
    """Poll QR code scan status. Returns { status: waiting|scanned|expired|confirmed }."""
    return await _bili_poll_qr(qrcode_key)


@app.get("/api/bilibili/status")
async def bilibili_status():
    """Check if Bilibili cookies are available."""
    path = _bili_cookie()
    return {"logged_in": path is not None, "cookie_file": path}


# ── Cookie Sync (Chrome extension bridge) ────────────────────────────────

@app.post("/api/cookies/sync")
async def cookies_sync(data: dict):
    """Save cookies from Chrome extension to Netscape file."""
    items = data.get("cookies", data.get("data", []))
    if isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list):
        items = []

    output, count = write_synced_cookiefile(items)
    return {"ok": True, "count": count, "file": output}


async def _run_on_startup():
    """Called by FastAPI startup event — refresh cookies if needed."""
    storage.init_db()
    run_startup_checks()
    try:
        await _bili_refresh()
    except Exception:
        pass


def _task_record_response(record) -> TaskRecordResponse:
    return TaskRecordResponse(
        task_id=record.task_id,
        task_type=record.task_type,
        status=record.status.value,
        percent=record.percent,
        result=record.result,
        error=record.error,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=getattr(record, "updated_at", ""),
    )


def _cache_video_info(url: str, info: dict) -> None:
    if not info:
        return
    for key in {url.strip(), str(info.get("webpage_url") or "").strip()}:
        if key:
            _info_cache[key] = info


def _find_requested_format(info: Optional[dict], format_id: str) -> Optional[dict]:
    if not info:
        return None
    for item in info.get("formats") or []:
        if str(item.get("format_id", "")) == str(format_id):
            return item
    return None


def _sync_legacy_progress(record) -> None:
    progress = get_progress(record.task_id)
    if not progress:
        return
    _persist_progress(record.task_id, progress)
    status = progress.get("status")
    if status:
        try:
            record.status = TaskStatus(status if status != "downloading" else "processing")
        except Exception:
            pass
    record.percent = float(progress.get("percent") or record.percent or 0)
    record.error = progress.get("error") or record.error
    result = record.result or {}
    for key in ("filename", "filesize_str", "speed", "eta"):
        if progress.get(key):
            result[key] = progress[key]
    record.result = result
    storage.update_task(
        record.task_id,
        status=record.status.value,
        percent=record.percent,
        result=result,
        error=record.error or "",
    )


def _persist_progress(task_id: str, progress: dict) -> None:
    raw_status = progress.get("status")
    status_map = {
        "queued": "queued",
        "downloading": "processing",
        "merging": "processing",
        "done": "done",
        "error": "error",
    }
    result = {
        key: progress.get(key)
        for key in ("filename", "filesize_str", "speed", "eta")
        if progress.get(key)
    }
    storage.update_task(
        task_id,
        status=status_map.get(raw_status, "processing"),
        percent=float(progress.get("percent") or 0),
        result=result or None,
        error=progress.get("error") or "",
    )


def _save_download_file(filename: Optional[str]) -> None:
    if not filename:
        return
    try:
        path = resolve_download_file(filename)
    except ValueError:
        return
    if not path.exists() or not path.is_file():
        return
    size = path.stat().st_size
    if size >= 1_000_000_000:
        size_str = f"{size/1_000_000_000:.1f} GB"
    elif size >= 1_000_000:
        size_str = f"{size/1_000_000:.1f} MB"
    elif size >= 1_000:
        size_str = f"{size/1_000:.1f} KB"
    else:
        size_str = f"{size} B"
    thumb = None
    for ext in (".jpg", ".png", ".webp"):
        candidate = path.with_suffix(ext)
        if candidate.exists():
            thumb = f"/api/download/{candidate.name}"
            break
    storage.save_file(path.name, size, size_str, str(path), thumb)


def _job_for_task(task_type: str):
    return {
        "download": _run_download_job,
        "subtitle": _run_subtitle_job,
        "summary": _run_summary_job,
        "mindmap": _run_mindmap_job,
        "ask": _run_ask_job,
        "transcribe": _run_transcribe_job,
        "convert": _run_convert_job,
        "rewrite": _run_rewrite_job,
    }.get(task_type)
