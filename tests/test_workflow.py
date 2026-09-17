from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from teamstorm_mcp.adapters.sqlite_closures import SQLiteClosureRepository
from teamstorm_mcp.adapters.workflow import load_workflow
from teamstorm_mcp.application.exceptions import TeamStormBadRequestError, TeamStormConnectionError
from teamstorm_mcp.application.interfaces.teamstorm import TeamStormGateway
from teamstorm_mcp.application.models import StatusReference, WorkItem
from teamstorm_mcp.application.scheduling import ClosureRequest, ClosureService
from teamstorm_mcp.application.services.closure_worker import ClosureWorker
from teamstorm_mcp.application.services.teamstorm import TeamStormService

NOW = datetime(2026, 9, 16, 10, tzinfo=UTC)
TEMPLATE = Path(__file__).parents[1] / "skills/teamstorm-workflow/SKILL.md"


def task(status: str) -> WorkItem:
    return WorkItem(id="1", key="TS-1", name="Task", status=StatusReference(id=status, name=status))


@pytest.fixture
async def setup(tmp_path: Path):
    workflow = load_workflow(TEMPLATE)
    assert workflow is not None
    gateway = AsyncMock(spec=TeamStormGateway)
    gateway.get_workitem.return_value = task("Ready")
    gateway.list_workitems.return_value = [task("Ready")]
    gateway.update_workitem.return_value = task("Done")
    repository = SQLiteClosureRepository(tmp_path / "queue.sqlite3")
    await repository.initialize()
    service = TeamStormService(gateway, workflow=workflow)
    closures = ClosureService(repository, service, workflow)
    worker = ClosureWorker(repository, service, workflow_service=service)
    return gateway, closures, worker, service


async def schedule(closures: ClosureService, when: datetime = NOW):
    return await closures.schedule(
        ClosureRequest(task_key="TS-1", close_at=when, target_status="Done")
    )


async def test_early_ready_waits_and_closes_once(setup) -> None:
    gateway, closures, worker, _ = setup
    first = await schedule(closures)
    assert await schedule(closures) == first
    assert await worker.tick(NOW - timedelta(seconds=1)) == 0
    gateway.update_workitem.assert_not_awaited()
    assert await worker.tick(NOW) == 1
    assert await worker.tick(NOW) == 0
    gateway.update_workitem.assert_awaited_once()
    assert (await closures.get("TS-1")).state == "completed"


async def test_manual_exit_and_late_return_keep_intent(setup) -> None:
    gateway, closures, worker, _ = setup
    gateway.get_workitem.return_value = task("In Progress")
    assert (await schedule(closures)).state == "waiting"
    gateway.get_workitem.return_value = task("Ready")
    await worker.tick(NOW - timedelta(seconds=2))
    assert (await closures.get("TS-1")).state == "pending"
    gateway.get_workitem.return_value = task("Review")
    await worker.tick(NOW)
    assert (await closures.get("TS-1")).state == "waiting"
    gateway.update_workitem.assert_not_awaited()
    gateway.get_workitem.return_value = task("Ready")
    assert await worker.tick(NOW + timedelta(hours=1)) == 1


@pytest.mark.parametrize("scenario", ["missing", "cancelled", "done", "changed_map"])
async def test_no_patch_without_valid_pending_intent(setup, scenario: str) -> None:
    gateway, closures, worker, service = setup
    if scenario != "missing":
        await schedule(closures)
    if scenario == "cancelled":
        await closures.cancel("TS-1")
    elif scenario == "done":
        gateway.get_workitem.return_value = task("Done")
    elif scenario == "changed_map":
        service.workflow.definition.revision += 1
    await worker.tick(NOW)
    gateway.update_workitem.assert_not_awaited()
    if scenario == "changed_map":
        assert (await closures.get("TS-1")).state == "suspended"
    elif scenario == "done":
        assert (await closures.get("TS-1")).state == "completed"


async def test_patch_failure_retries(setup) -> None:
    gateway, closures, worker, _ = setup
    await schedule(closures)
    gateway.update_workitem.side_effect = TeamStormConnectionError("offline")
    assert await worker.tick(NOW) == 0
    assert (await closures.get("TS-1")).state == "pending"
    gateway.update_workitem.side_effect = None
    assert await worker.tick(NOW) == 1


@pytest.mark.parametrize("change", ["cancel", "reschedule", "status"])
async def test_rechecks_before_final_write(setup, change: str) -> None:
    gateway, closures, worker, _ = setup
    await schedule(closures)
    calls = 0

    async def read(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change == "cancel":
                await closures.cancel("TS-1")
            elif change == "reschedule":
                await schedule(closures, NOW + timedelta(hours=1))
            else:
                return task("Review")
        return task("Ready")

    gateway.get_workitem.side_effect = read
    assert await worker.tick(NOW) == 0
    gateway.update_workitem.assert_not_awaited()


async def test_mcp_enforces_edges_and_actor(setup) -> None:
    gateway, _, _, service = setup
    await service.update_task("TS-1", status="Ready")
    gateway.update_workitem.assert_not_awaited()
    with pytest.raises(TeamStormBadRequestError):
        await service.update_task("TS-1", status="Done")
    with pytest.raises(TeamStormBadRequestError):
        await service.update_task("TS-1", status="Backlog")
    await service.update_task("TS-1", status="In Progress")
    gateway.update_workitem.assert_awaited_once()


@pytest.mark.parametrize(
    "old,new",
    [
        ("schema_version: 1", "schema_version: 2"),
        ("actor: daemon", "actor: mcp"),
        ("missing_deadline: skip", "missing_deadline: now"),
        ("revision: 1", "revision: 1\nrevision: 2"),
    ],
)
def test_invalid_map_rejected(tmp_path: Path, old: str, new: str) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(TEMPLATE.read_text().replace(old, new))
    with pytest.raises(ValueError):
        load_workflow(path)
