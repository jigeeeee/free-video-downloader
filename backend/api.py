"""FastAPI application — Video Downloader API."""

import os
import uuid
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
from backend.models import (
    URLRequest, VideoInfo, DownloadRequest, DownloadTask,
    FileInfo, FileListResponse
)
from backend.downloader import extract_info, download, get_progress

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
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    
    # Try cache first, then parse, then skip validation (URL was already validated by /api/info)
    cache_key = req.url.strip()
    info = _info_cache.get(cache_key)
    direct_url = None
    if info is None:
        try:
            info = await asyncio.to_thread(extract_info, req.url)
            _info_cache[cache_key] = info
        except Exception:
            # Parse failed — proceed anyway with just the URL
            info = {}
    video_urls = info.get("_video_urls") if info else None
    audio_urls = info.get("_audio_urls") if info else None
    background_tasks.add_task(download, req.url, req.format_id, task_id, video_urls, audio_urls)
    return DownloadTask(task_id=task_id, status="queued")


@app.get("/api/progress/{task_id}", response_model=DownloadTask)
async def get_download_progress(task_id: str):
    progress = get_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return DownloadTask(**progress)


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





