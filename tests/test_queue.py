import pytest

from backend import queue


@pytest.mark.asyncio
async def test_queue_exposes_concise_job_error(monkeypatch):
    monkeypatch.setattr(queue.storage, "list_tasks", lambda limit=200: [])
    monkeypatch.setattr(queue.storage, "create_task", lambda *args, **kwargs: None)
    monkeypatch.setattr(queue.storage, "update_task", lambda *args, **kwargs: None)

    async def failing_job(task_id: str, **kwargs):
        raise RuntimeError("Subtitle track is unavailable")

    backend = queue._InMemoryBackend(max_concurrent=1)
    task_id = await backend.enqueue("subtitle", failing_job)
    await backend._running[task_id]

    record = backend.get(task_id)
    assert record is not None
    assert record.status == queue.TaskStatus.ERROR
    assert record.error == "Subtitle track is unavailable"
