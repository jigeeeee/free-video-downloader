"""Small SQLite persistence layer for tasks, files, and AI results."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

DB_PATH = Path(getattr(config, "DB_PATH", Path(config.DOWNLOAD_DIR) / "video_downloader.db"))
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                percent REAL NOT NULL DEFAULT 0,
                result TEXT,
                error TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                name TEXT PRIMARY KEY,
                size INTEGER NOT NULL DEFAULT 0,
                size_str TEXT,
                path TEXT,
                thumbnail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                result_type TEXT NOT NULL,
                title TEXT,
                url TEXT,
                result TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            UPDATE tasks
               SET status = 'error',
                   error = COALESCE(error, 'Interrupted by server restart'),
                   updated_at = ?
             WHERE status IN ('queued', 'processing')
            """,
            (_now(),),
        )


def create_task(task_id: str, task_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    now = _now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks
                (task_id, task_type, status, percent, result, error, metadata, created_at, updated_at)
            VALUES (?, ?, 'queued', 0, NULL, NULL, ?, ?, ?)
            """,
            (task_id, task_type, _json_dumps(metadata or {}), now, now),
        )


def update_task(
    task_id: str,
    *,
    status: Optional[str] = None,
    percent: Optional[float] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    fields = ["updated_at = ?"]
    values: List[Any] = [_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if percent is not None:
        fields.append("percent = ?")
        values.append(percent)
    if result is not None:
        fields.append("result = ?")
        values.append(_json_dumps(result))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if metadata is not None:
        fields.append("metadata = ?")
        values.append(_json_dumps(metadata))
    values.append(task_id)
    with _LOCK, _connect() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?", values)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def list_tasks(limit: int = 100) -> List[Dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY datetime(created_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def _task_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "task_type": row["task_type"],
        "status": row["status"],
        "percent": row["percent"],
        "result": _json_loads(row["result"], {}),
        "error": row["error"],
        "metadata": _json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_file(name: str, size: int, size_str: str, path: str, thumbnail: Optional[str] = None) -> None:
    now = _now()
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO files (name, size, size_str, path, thumbnail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                size = excluded.size,
                size_str = excluded.size_str,
                path = excluded.path,
                thumbnail = excluded.thumbnail,
                updated_at = excluded.updated_at
            """,
            (name, size, size_str, path, thumbnail, now, now),
        )


def save_ai_result(task_id: str, result_type: str, result: Dict[str, Any], title: str = "", url: str = "") -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_results (task_id, result_type, title, url, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, result_type, title, url, _json_dumps(result), _now()),
        )


def list_history(limit: int = 100) -> Dict[str, Any]:
    with _LOCK, _connect() as conn:
        files = conn.execute(
            "SELECT * FROM files ORDER BY datetime(updated_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        ai_rows = conn.execute(
            "SELECT * FROM ai_results ORDER BY datetime(created_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {
        "files": [dict(row) for row in files],
        "ai_results": [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "result_type": row["result_type"],
                "title": row["title"],
                "url": row["url"],
                "result": _json_loads(row["result"], {}),
                "created_at": row["created_at"],
            }
            for row in ai_rows
        ],
    }
