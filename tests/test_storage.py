from backend import storage


def test_task_lifecycle_uses_temp_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_tasks.db")

    storage.init_db()
    storage.create_task("task-1", "download", {"url": "https://example.com/video"})
    storage.update_task("task-1", status="processing", percent=42.5)
    storage.update_task("task-1", status="done", percent=100, result={"filename": "video.mp4"}, error="")

    task = storage.get_task("task-1")
    assert task["task_id"] == "task-1"
    assert task["task_type"] == "download"
    assert task["status"] == "done"
    assert task["percent"] == 100
    assert task["result"] == {"filename": "video.mp4"}
    assert task["metadata"] == {"url": "https://example.com/video"}

    listed = storage.list_tasks()
    assert [item["task_id"] for item in listed] == ["task-1"]


def test_history_persists_files_and_ai_results(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_history.db")

    storage.init_db()
    storage.save_file("video.mp4", 1234, "1.2 KB", str(tmp_path / "video.mp4"), thumbnail="thumb.webp")
    storage.save_ai_result(
        "task-2",
        "summary",
        {"one_liner": "hello", "tags": ["demo"]},
        title="Video",
        url="https://example.com/video",
    )

    history = storage.list_history()
    assert history["files"][0]["name"] == "video.mp4"
    assert history["files"][0]["size"] == 1234
    assert history["ai_results"][0]["task_id"] == "task-2"
    assert history["ai_results"][0]["result"] == {"one_liner": "hello", "tags": ["demo"]}


def test_init_db_marks_interrupted_tasks_as_error(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_interrupted.db")

    storage.init_db()
    storage.create_task("task-3", "download", {})
    storage.update_task("task-3", status="processing", percent=20)

    storage.init_db()

    task = storage.get_task("task-3")
    assert task["status"] == "error"
    assert task["error"] == "Interrupted by server restart"
