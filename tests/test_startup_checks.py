import config
from backend import startup_checks


def test_startup_checks_report_external_dependency_configuration(monkeypatch, tmp_path):
    cookiefile = tmp_path / "cookies.txt"
    cookiefile.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    monkeypatch.setattr(config, "DOWNLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(config, "COOKIES_BROWSER", "")
    monkeypatch.setattr(config, "YOUTUBE_PO_TOKEN", "web.gvs+token")
    monkeypatch.setattr(config, "YOUTUBE_VISITOR_DATA", "visitor")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(
        startup_checks,
        "_detect_cookie_status",
        lambda: {
            "browser": None,
            "generic_cookiefile": str(cookiefile),
            "platforms": {
                "youtube": {"has_cookie_source": True, "cookiefile": str(cookiefile)},
                "bilibili": {"has_cookie_source": True, "cookiefile": str(cookiefile)},
                "douyin": {"has_cookie_source": True, "cookiefile": str(cookiefile)},
            },
        },
    )

    checks = startup_checks.run_startup_checks()

    assert "missing_required" in checks
    assert "warnings" in checks
    assert checks["cookies"]["cookiefile"] == str(cookiefile)
    assert checks["cookies"]["has_cookie_source"] is True
    assert checks["cookies"]["platforms"]["youtube"]["has_cookie_source"] is True
    assert checks["youtube"]["po_token_configured"] is True
    assert checks["youtube"]["visitor_data_configured"] is True
    assert checks["ai"]["deepseek_api_key_configured"] is True
