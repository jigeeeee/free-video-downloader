"""Pydantic data models for the video downloader API."""

from typing import Optional, List
from pydantic import BaseModel, field_validator


class URLRequest(BaseModel):
    url: str


class FormatInfo(BaseModel):
    format_id: str
    resolution: str
    ext: str
    filesize: Optional[int] = None
    filesize_str: Optional[str] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    video_only: bool = False


class VideoInfo(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None       # seconds — Bilibili returns fractional
    duration_str: Optional[str] = None
    platform: Optional[str] = None
    uploader: Optional[str] = None
    formats: List[FormatInfo] = []
    webpage_url: Optional[str] = None


class DownloadRequest(BaseModel):
    url: str
    format_id: str = "bestvideo+bestaudio/best"


class DownloadTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None
    filesize_str: Optional[str] = None
    error: Optional[str] = None


class FileInfo(BaseModel):
    name: str
    size: int
    size_str: str
    date: str


class FileListResponse(BaseModel):
    files: List[FileInfo]
