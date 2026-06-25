"""Universal Video Downloader — entry point."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
import config

if __name__ == "__main__":
    print("=" * 50)
    print("  Universal Video Downloader v1.0")
    print("=" * 50)
    print(f"  API:  http://{config.HOST}:{config.PORT}")
    print(f"  Docs: http://{config.HOST}:{config.PORT}/docs")
    print(f"  Downloads: {config.DOWNLOAD_DIR}")
    if config.COOKIES_BROWSER:
        print(f"  Cookies: from {config.COOKIES_BROWSER} browser")
    else:
        print(f"  Cookies: from cookies.txt (if exists)")
    print("=" * 50)
    uvicorn.run(
        "backend.api:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info",
    )
