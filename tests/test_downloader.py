from pathlib import Path

import backend.downloader as downloader


def test_normalize_url_handles_douyin_modal_and_youtube_shorts():
    assert (
        downloader._normalize_url("https://www.douyin.com/user/abc?modal_id=7381234567890123456")
        == "https://www.douyin.com/video/7381234567890123456"
    )
    assert (
        downloader._normalize_url("https://www.youtube.com/shorts/QKZMPs5S8Mg")
        == "https://www.youtube.com/watch?v=QKZMPs5S8Mg"
    )


def test_format_candidates_keep_explicit_youtube_video_quality_strict():
    requested = {
        "format_id": "299",
        "resolution": "1080p",
        "ext": "mp4",
        "video_only": True,
    }

    candidates = downloader._format_candidates("299", requested, "YouTube")

    assert candidates == ["299+bestaudio"]
    assert all("/best" not in candidate for candidate in candidates)


def test_format_candidates_allow_default_fallback_only_without_requested_format():
    assert downloader._format_candidates("", None, "YouTube") == [
        "bestvideo+bestaudio/best",
        "best",
    ]


def test_format_candidates_add_audio_fallback_for_audio_only_selection():
    requested = {
        "format_id": "251",
        "resolution": "audio only",
        "ext": "webm",
        "video_only": False,
    }

    assert downloader._format_candidates("251", requested, "YouTube") == ["251", "bestaudio"]


def test_drm_errors_are_terminal_not_retryable():
    message = "ERROR: [youtube] 7SmxBOGWin0: This video is DRM protected"

    assert downloader._is_drm_error(message)
    assert not downloader._is_download_retryable_error(message)
    assert "cannot bypass DRM" in downloader._format_drm_error("YouTube")


def test_parse_info_picks_best_display_format_per_resolution_and_extension():
    parsed = downloader._parse_info(
        {
            "title": "Example",
            "duration": 487,
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
            "formats": [
                {"format_id": "18", "height": 360, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "tbr": 400},
                {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 1200},
                {"format_id": "299", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 2500},
                {"format_id": "303", "height": 1080, "ext": "webm", "vcodec": "vp9", "acodec": "none", "tbr": 2100},
                {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160},
                {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none"},
            ],
        },
        "https://www.youtube.com/watch?v=abc123",
    )

    formats = {(item["resolution"], item["ext"]): item for item in parsed["formats"]}
    assert parsed["duration_str"] == "8:07"
    assert parsed["platform"] == "YouTube"
    assert formats[("1080p", "mp4")]["format_id"] == "299"
    assert formats[("1080p", "webm")]["format_id"] == "303"
    assert formats[("audio only", "webm")]["format_id"] == "251"
    assert ("other", "mhtml") not in formats


def test_downloaded_format_match_requires_requested_format_id():
    path = Path("Title [task123-QKZMPs5S8Mg-299+251].mp4")

    assert downloader._downloaded_format_matches(path, "task123", {"format_id": "299"})
    assert not downloader._downloaded_format_matches(path, "task123", {"format_id": "18"})
    assert not downloader._downloaded_format_matches(path, "other", {"format_id": "299"})


def test_format_id_from_downloaded_name():
    path = Path("Title [task123-QKZMPs5S8Mg-699+251].webm")

    assert downloader._format_id_from_downloaded_name(path, "task123") == "699+251"


def test_newest_media_file_accepts_audio_outputs(monkeypatch, tmp_path):
    audio = tmp_path / "Title [task123-abc-30280].m4a"
    audio.write_bytes(b"audio")

    monkeypatch.setattr(downloader.config, "DOWNLOAD_DIR", str(tmp_path))

    found = downloader._newest_media_file(0, marker="task123")

    assert found == audio


def test_newest_media_file_ignores_yt_dlp_fragments(monkeypatch, tmp_path):
    fragment = tmp_path / "Title [task123-abc-30120+30280].f30120.mp4"
    final = tmp_path / "Title [task123-abc-30120+30280].mp4"
    fragment.write_bytes(b"fragment")
    final.write_bytes(b"final")

    monkeypatch.setattr(downloader.config, "DOWNLOAD_DIR", str(tmp_path))

    assert downloader._newest_media_file(0, marker="task123") == final


def test_cleanup_failed_download_outputs_removes_only_task_fragments(monkeypatch, tmp_path):
    fragment = tmp_path / "Title [task123-abc-30120+30280].f30120.mp4"
    part = tmp_path / "Title [task123-abc-30120+30280].f30120.mp4.part"
    final = tmp_path / "Title [task123-abc-30120+30280].mp4"
    other = tmp_path / "Title [other-abc-30120+30280].f30120.mp4"
    for path in (fragment, part, final, other):
        path.write_bytes(b"x")

    monkeypatch.setattr(downloader.config, "DOWNLOAD_DIR", str(tmp_path))

    removed = downloader._cleanup_failed_download_outputs("task123")

    assert fragment.name in removed
    assert part.name in removed
    assert not fragment.exists()
    assert not part.exists()
    assert final.exists()
    assert other.exists()


def test_resolve_youtube_equivalent_video_only_format_stays_strict(monkeypatch):
    import yt_dlp

    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "formats": [
                    {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 1200},
                    {"format_id": "299", "height": 1080, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 2500},
                    {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160},
                ]
            }

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(downloader, "_build_opts", lambda **kwargs: {})

    candidate, resolved = downloader._resolve_youtube_equivalent_format(
        "https://www.youtube.com/watch?v=abc123",
        "ios",
        {"format_id": "137", "resolution": "1080p", "ext": "mp4", "fps": 30, "video_only": True},
        "137+bestaudio",
    )

    assert candidate == "137+bestaudio"
    assert "/best" not in candidate
    assert resolved["format_id"] == "137"
    assert resolved["video_only"] is True
