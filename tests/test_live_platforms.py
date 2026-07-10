import os

import pytest

from backend.downloader import extract_info


pytestmark = pytest.mark.live


def _env_url(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"Set {name} to run this live platform test")
    return value


@pytest.mark.parametrize(
    ("env_name", "expected_platform"),
    [
        ("LIVE_YOUTUBE_URL", "YouTube"),
        ("LIVE_BILIBILI_URL", "Bilibili"),
        ("LIVE_DOUYIN_URL", "Douyin"),
    ],
)
def test_live_extract_info_smoke(env_name, expected_platform):
    info = extract_info(_env_url(env_name))

    assert info["title"]
    assert info["platform"] == expected_platform
    assert info["formats"]
