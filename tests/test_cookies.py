import config
from backend import cookies


def test_write_synced_cookiefiles_splits_platform_files(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))

    result = cookies.write_synced_cookiefiles([
        {"domain": ".youtube.com", "name": "SID", "value": "yt", "path": "/", "secure": True},
        {"domain": ".bilibili.com", "name": "SESSDATA", "value": "bili", "path": "/", "secure": True},
        {"domain": ".douyin.com", "name": "sessionid", "value": "dy", "path": "/", "secure": True},
    ])

    assert result["count"] == 3
    assert result["platforms"]["youtube"]["count"] == 1
    assert result["platforms"]["bilibili"]["count"] == 1
    assert result["platforms"]["douyin"]["count"] == 1
    assert (tmp_path / "cookies" / "youtube.txt").read_text(encoding="utf-8").count("SID") == 1
    assert (tmp_path / "cookies" / "douyin.txt").read_text(encoding="utf-8").count("sessionid") == 1


def test_get_cookiefile_prefers_matching_platform_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)

    cookie_dir = tmp_path / "cookies"
    cookie_dir.mkdir()
    youtube = cookie_dir / "youtube.txt"
    douyin = cookie_dir / "douyin.txt"
    generic = tmp_path / "cookies.txt"
    youtube.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1\tSID\tyt\n", encoding="utf-8")
    douyin.write_text("# Netscape HTTP Cookie File\n.douyin.com\tTRUE\t/\tTRUE\t1\tsessionid\tdy\n", encoding="utf-8")
    generic.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t1\tA\tB\n", encoding="utf-8")

    assert cookies.get_cookiefile("https://www.youtube.com/watch?v=abc") == str(youtube)
    assert cookies.get_cookiefile("https://www.douyin.com/video/123") == str(douyin)


def test_apply_cookie_options_uses_browser_as_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(config, "COOKIES_BROWSER", "firefox")

    opts = {}
    cookies.apply_cookie_options(opts, url="https://www.youtube.com/watch?v=abc")

    assert opts["cookiesfrombrowser"] == ("firefox",)
