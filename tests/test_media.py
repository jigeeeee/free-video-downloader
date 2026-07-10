from pathlib import Path

import pytest

import config
from backend import media


def test_safe_filename_removes_path_and_invalid_characters():
    assert media.safe_filename("../bad:name?.mp4") == "bad_name_.mp4"
    assert media.safe_filename("   ...   ", "fallback.mp4") == "fallback.mp4"


def test_resolve_download_file_rejects_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))

    resolved = media.resolve_download_file("video.mp4")
    assert resolved == (tmp_path / "video.mp4").resolve()

    with pytest.raises(ValueError, match="Invalid file path"):
        media.resolve_download_file("../escape.mp4")

    with pytest.raises(ValueError, match="Invalid file path"):
        media.resolve_download_file("nested\\escape.mp4")


def test_format_size_is_human_readable():
    assert media._format_size(999) == "999 B"
    assert media._format_size(1500) == "1.5 KB"
    assert media._format_size(2_500_000) == "2.5 MB"
    assert media._format_size(3_500_000_000) == "3.5 GB"
