"""Universal Video Downloader — global config."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(ROOT_DIR / "downloads"))
SUBTITLE_DIR = os.environ.get("SUBTITLE_DIR", str(ROOT_DIR / "downloads" / "subtitles"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8001"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))

# Cookie: "" = use cookies.txt (recommended; Bilibili + Douyin both supported)
#         "chrome" = read from Chrome browser (requires Chrome closed)
COOKIES_BROWSER = os.environ.get("YTDLP_COOKIES_BROWSER", "")

Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(SUBTITLE_DIR).mkdir(parents=True, exist_ok=True)
