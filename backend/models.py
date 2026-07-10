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
    requested_format_id: Optional[str] = None
    resolved_format_id: Optional[str] = None
    actual_format_id: Optional[str] = None
    format_selector: Optional[str] = None


class FileInfo(BaseModel):
    name: str
    size: int
    size_str: str
    date: str
    thumbnail: Optional[str] = None


class FileListResponse(BaseModel):
    files: List[FileInfo]


# ── Subtitle models ──────────────────────────────────────────────────────

class SubtitleRequest(BaseModel):
    url: str
    languages: Optional[List[str]] = None   # e.g. ["en", "zh-Hans"]; None = auto


class SubtitleLang(BaseModel):
    code: str
    source: str = "manual"   # "manual" | "auto"


class SubtitleSegment(BaseModel):
    index: int
    start: str                # "00:01:23"
    end: str                  # "00:01:25"
    start_sec: float
    text: str


class SubtitleEntry(BaseModel):
    lang: str
    source: str
    text_preview: str
    txt_path: str
    srt_path: str
    line_count: int
    segment_count: int = 0
    segments: List[SubtitleSegment] = []


class SubtitleResult(BaseModel):
    video_id: str
    title: str
    available_langs: List[SubtitleLang] = []
    extracted: List[SubtitleEntry] = []


class SubtitleTask(BaseModel):
    task_id: str
    status: str = "queued"       # queued | processing | done | error
    percent: float = 0.0
    result: Optional[SubtitleResult] = None
    error: Optional[str] = None


# ── AI Summary models ────────────────────────────────────────────────────

class SummaryRequest(BaseModel):
    url: str
    lang: str = "zh"                   # "zh" | "en"


class ChapterItem(BaseModel):
    timestamp: str                     # e.g. "01:23"
    title: str


class SummaryResult(BaseModel):
    one_liner: str = ""
    chapters: List[ChapterItem] = []
    key_points: List[str] = []
    tags: List[str] = []
    video_title: str = ""
    tokens_used: Optional[dict] = None
    error: Optional[str] = None


class SummaryTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[SummaryResult] = None
    error: Optional[str] = None


# ── Mindmap models ───────────────────────────────────────────────────────

class MindmapRequest(BaseModel):
    url: str
    lang: str = "zh"


class MindmapResult(BaseModel):
    mindmap_text: str = ""
    video_title: str = ""
    tokens_used: Optional[dict] = None


class MindmapTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[MindmapResult] = None
    error: Optional[str] = None


# ── AI Q&A models ────────────────────────────────────────────────────────

class ChatTurn(BaseModel):
    question: str
    answer: str = ""


class AskRequest(BaseModel):
    url: str
    question: str
    lang: str = "zh"
    history: List[ChatTurn] = []      # previous Q&A turns for multi-turn context


class AskResponse(BaseModel):
    question: str
    answer: str
    video_title: str = ""
    tokens_used: Optional[dict] = None


class AskTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[AskResponse] = None
    error: Optional[str] = None


# ── Transcribe models ────────────────────────────────────────────────────

class TranscribeTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None


# ── Batch models ─────────────────────────────────────────────────────────

class BatchRequest(BaseModel):
    urls: List[str]                                    # list of video URLs


class BatchTaskInfo(BaseModel):
    task_id: str
    url: str
    task_type: str                                     # "download" | "summary" | etc.
    status: str


class BatchResponse(BaseModel):
    batch_id: str
    tasks: List[BatchTaskInfo] = []
    total: int = 0
    done: int = 0
    processing: int = 0
    queued: int = 0
    error: int = 0


# ── Translate models ─────────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "简体中文"


class TranslateResponse(BaseModel):
    translated_text: str
    target_lang: str
    tokens_used: Optional[dict] = None


# ── Unified task/history and add-on feature models ───────────────────────

class TaskRecordResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    percent: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""


class TaskListResponse(BaseModel):
    tasks: List[TaskRecordResponse] = []


class HistoryResponse(BaseModel):
    files: List[dict] = []
    ai_results: List[dict] = []


class ConvertRequest(BaseModel):
    filename: str
    target_format: str = "mp3"
    mode: str = "audio"              # audio | convert | compress
    bitrate: Optional[str] = None


class ConvertTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None


class RewriteRequest(BaseModel):
    url: Optional[str] = None
    title: str = ""
    text: Optional[str] = None
    style: str = "notes"             # wechat | xiaohongshu | twitter | notes | markdown
    lang: str = "zh"


class RewriteTask(BaseModel):
    task_id: str
    status: str = "queued"
    percent: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
