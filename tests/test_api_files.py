from backend import api


def test_library_media_filter_excludes_yt_dlp_fragments(tmp_path):
    final = tmp_path / "Title [task-abc-30120+30280].mp4"
    fragment = tmp_path / "Title [task-abc-30120+30280].f30120.mp4"
    part = tmp_path / "Title [task-abc-30120+30280].f30120.mp4.part"
    for path in (final, fragment, part):
        path.write_bytes(b"x")

    assert api._is_library_media_file(final)
    assert not api._is_library_media_file(fragment)
    assert not api._is_library_media_file(part)
