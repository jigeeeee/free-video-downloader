"""Universal Video Downloader — global config."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(ROOT_DIR / "downloads"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8001"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))

# Cookie: "" = use cookies.txt (recommended; Bilibili + Douyin both supported)
#         "chrome" = read from Chrome browser (requires Chrome closed)
COOKIES_BROWSER = os.environ.get("YTDLP_COOKIES_BROWSER", "")

Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
