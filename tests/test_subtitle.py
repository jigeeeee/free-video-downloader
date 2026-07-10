import config
from backend import subtitle


def test_youtube_subtitle_info_skips_media_format_processing():
    calls = []

    class FakeYdl:
        def extract_info(self, *args, **kwargs):
            calls.append((args, kwargs))
            return {"automatic_captions": {"en": []}}

    subtitle._extract_subtitle_info(
        FakeYdl(), "https://www.youtube.com/watch?v=abc12345678", "YouTube"
    )

    assert calls == [
        (("https://www.youtube.com/watch?v=abc12345678",), {"download": False, "process": False})
    ]


def test_download_youtube_subtitle_tracks_prefers_vtt_and_writes_caption(tmp_path):
    class Response:
        def read(self):
            return b"WEBVTT\\n\\n00:00:00.000 --> 00:00:01.000\\nHello"

        def close(self):
            pass

    class FakeYdl:
        def __init__(self):
            self.urls = []

        def urlopen(self, url):
            self.urls.append(url)
            return Response()

    ydl = FakeYdl()
    downloaded = subtitle._download_youtube_subtitle_tracks(
        ydl,
        {
            "id": "abc12345678",
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.test/json3"},
                    {"ext": "vtt", "url": "https://example.test/vtt"},
                ]
            },
        },
        str(tmp_path),
        ["en"],
    )

    assert downloaded == ["en"]
    assert ydl.urls == ["https://example.test/vtt"]
    assert (tmp_path / "abc12345678.en.vtt").read_text(encoding="utf-8").startswith("WEBVTT")


def test_youtube_subtitle_opts_include_client_retry_and_cookies(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(config, "COOKIES_BROWSER", "")

    opts = subtitle._build_subtitle_opts(
        out_dir=str(tmp_path / "subs"),
        download=True,
        languages=["en"],
        url="https://www.youtube.com/watch?v=abc12345678",
        client="ios",
    )

    assert opts["retries"] == 20
    assert opts["fragment_retries"] == 20
    assert opts["http_headers"]["Referer"] == "https://www.youtube.com/"
    assert opts["extractor_args"]["youtube"]["player_client"] == ["ios"]
    assert opts["subtitleslangs"] == ["en"]


def test_format_subtitle_failure_mentions_youtube_retry_help():
    message = subtitle._format_subtitle_failure("YouTube", "timeout")

    assert "multiple clients" in message
    assert "timeout" in message
