from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from teamstorm_mcp.adapters.sqlite_closures import SQLiteClosureRepository
from teamstorm_mcp.application.exceptions import TeamStormConnectionError
from teamstorm_mcp.application.interfaces.task_status import TaskStatusContextProvider
from teamstorm_mcp.application.models import StatusReference, WorkItem
from teamstorm_mcp.application.scheduling import ClosureRequest, ClosureService
from teamstorm_mcp.application.services.closure_worker import ClosureWorker

NOW = datetime(2026, 9, 16, 10, tzinfo=UTC)


@pytest.fixture
async def repository(tmp_path: Path) -> SQLiteClosureRepository:
    result = SQLiteClosureRepository(tmp_path / "queue.sqlite3")
    await result.initialize()
    return result


@pytest.fixture
def provider() -> AsyncMock:
    result = AsyncMock(spec=TaskStatusContextProvider)
    result.get_task.return_value = WorkItem(
        id="1", key="TS-1", name="Task", status=StatusReference(id="doing", name="Doing")
    )
    return result


def request(**changes: object) -> ClosureRequest:
    return ClosureRequest.model_validate(
        {"task_key": "TS-1", "close_at": NOW, "target_status": "Done", **changes}
    )


async def test_schedule_survives_reopen_and_normalizes_time(
    repository: SQLiteClosureRepository, provider: AsyncMock
) -> None:
    service = ClosureService(repository, provider)
    await service.schedule(request(task_key=" ts-1 ", close_at="2026-09-16T15:00:00+05:00"))
    reopened = SQLiteClosureRepository(repository.path)
    await reopened.initialize()
    saved = await reopened.get("TS-1")
    assert saved is not None
    assert saved.close_at == NOW
    assert saved.state == "pending"
    provider.get_task.assert_awaited_once_with("TS-1")


@pytest.mark.parametrize("delta", [timedelta(), timedelta(seconds=-1)])
async def test_worker_handles_due_and_overdue_but_not_future_tasks(
    repository: SQLiteClosureRepository, provider: AsyncMock, delta: timedelta
) -> None:
    await repository.schedule(request(close_at=NOW + delta))
    await repository.schedule(request(task_key="TS-2", close_at=NOW + timedelta(seconds=1)))
    worker = ClosureWorker(repository, provider)
    assert await worker.tick(NOW) == 1
    saved = await repository.get("TS-1")
    assert saved is not None
    assert saved.state == "context_ready"
    assert saved.current_status == StatusReference(id="doing", name="Doing")
    assert saved.checked_at == NOW
    future = await repository.get("TS-2")
    assert future is not None and future.state == "pending"
    assert await worker.tick(NOW) == 0
    provider.get_task.assert_awaited_once_with("TS-1")


async def test_identical_request_is_idempotent_and_reschedule_resets_context(
    repository: SQLiteClosureRepository, provider: AsyncMock
) -> None:
    original = await repository.schedule(request())
    await ClosureWorker(repository, provider).tick(NOW)
    repeated = await repository.schedule(request())
    assert repeated.state == "context_ready"
    assert repeated.revision == original.revision
    changed = await repository.schedule(request(close_at=NOW + timedelta(hours=1)))
    assert changed.state == "pending"
    assert changed.current_status is None
    assert changed.revision == original.revision + 1


async def test_stale_context_does_not_overwrite_rescheduled_task(
    repository: SQLiteClosureRepository,
) -> None:
    original = await repository.schedule(request())
    await repository.schedule(request(target_status="Review"))
    await repository.schedule(request())
    assert not await repository.save_context(original, None, NOW)
    saved = await repository.get("TS-1")
    assert saved is not None and saved.state == "pending"


async def test_failure_keeps_request_for_retry_and_does_not_block_other_tasks(
    repository: SQLiteClosureRepository, provider: AsyncMock
) -> None:
    await repository.schedule(request())
    await repository.schedule(request(task_key="TS-2"))
    task = provider.get_task.return_value
    provider.get_task.side_effect = [TeamStormConnectionError("offline"), task]
    worker = ClosureWorker(repository, provider)
    assert await worker.tick(NOW) == 1
    failed = await repository.get("TS-1")
    assert failed is not None and failed.state == "pending"
    provider.get_task.side_effect = None
    assert await worker.tick(NOW) == 1


async def test_failed_lookup_does_not_schedule(
    repository: SQLiteClosureRepository, provider: AsyncMock
) -> None:
    provider.get_task.side_effect = TeamStormConnectionError("offline")
    with pytest.raises(TeamStormConnectionError):
        await ClosureService(repository, provider).schedule(request())
    assert await repository.get("TS-1") is None


def test_schedule_rejects_naive_time() -> None:
    with pytest.raises(ValidationError):
        request(close_at="2026-09-16T10:00:00")
