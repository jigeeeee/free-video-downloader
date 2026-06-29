"""Universal Video Downloader — global config."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(ROOT_DIR / "downloads"))
SUBTITLE_DIR = os.environ.get("SUBTITLE_DIR", str(ROOT_DIR / "downloads" / "subtitles"))
DB_PATH = os.environ.get("DB_PATH", str(Path(DOWNLOAD_DIR) / "video_downloader.db"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8002"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))

# Cookie: "" = use cookies.txt (recommended)
#         "chrome" = auto-read Chrome cookies (close Chrome first)
COOKIES_BROWSER = os.environ.get("YTDLP_COOKIES_BROWSER", "")

# Optional YouTube PO Token support for stricter GVS/CDN checks.
# Example: web.gvs+TOKEN_VALUE
YOUTUBE_PO_TOKEN = os.environ.get("YTDLP_YOUTUBE_PO_TOKEN", "")
YOUTUBE_VISITOR_DATA = os.environ.get("YTDLP_YOUTUBE_VISITOR_DATA", "")

Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(SUBTITLE_DIR).mkdir(parents=True, exist_ok=True)
