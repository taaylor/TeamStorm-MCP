import asyncio
import logging
from datetime import UTC, datetime

from teamstorm_mcp.application.exceptions import TeamStormError
from teamstorm_mcp.application.interfaces.task_status import TaskStatusContextProvider
from teamstorm_mcp.application.scheduling import ClosureRepository, ScheduledClosure
from teamstorm_mcp.application.services.teamstorm import TeamStormService

logger = logging.getLogger(__name__)


class ClosureWorker:
    """Finalize scheduled tasks, or prepare contexts when no map is configured."""

    def __init__(
        self,
        repository: ClosureRepository,
        status_context: TaskStatusContextProvider,
        *,
        workflow_service: TeamStormService | None = None,
    ) -> None:
        self.repository = repository
        self.status_context = status_context
        self.workflow_service = workflow_service

    async def tick(self, now: datetime | None = None) -> int:
        checked_at = now or datetime.now(UTC)
        if checked_at.utcoffset() is None:
            raise ValueError("Worker time must include a timezone")
        if self.workflow_service is not None:
            return await self._finalize(checked_at)
        prepared = 0
        for request in await self.repository.due(checked_at):
            try:
                task = await self.status_context.get_task(request.task_key)
            except TeamStormError:
                logger.warning("Could not read status for %s; will retry", request.task_key)
                continue
            if await self.repository.save_context(request, task.status, checked_at):
                prepared += 1
                logger.info("Status context ready for %s", request.task_key)
        return prepared

    async def _finalize(self, now: datetime) -> int:
        service = self.workflow_service
        assert service is not None and service.workflow is not None
        definition = service.workflow.definition
        rule = definition.scheduled_finalization
        try:
            tasks = await service.list_tasks()
        except TeamStormError:
            logger.warning("Could not discover tasks; will retry")
            return 0
        completed = 0
        for discovered in tasks:
            request = await self.repository.get(discovered.key)
            if request is None or request.state in {"completed", "cancelled", "suspended"}:
                continue
            try:
                if (
                    request.workflow_id != definition.id
                    or request.workflow_revision != definition.revision
                    or request.workflow_fingerprint != definition.fingerprint
                ):
                    await self.repository.set_state(
                        request, "suspended", request.current_status, now
                    )
                    continue
                task = await service.get_task(request.task_key)
                current = definition.resolve(task.status)
                state = "waiting"
                if current == rule.final_state:
                    state = "completed"
                elif current == rule.trigger_state:
                    state = "pending"
                    if request.close_at <= now:

                        async def unchanged(request: ScheduledClosure = request) -> bool:
                            latest = await self.repository.get(request.task_key)
                            return latest == request

                        task = await service.finalize_task(request.task_key, before_write=unchanged)
                        if definition.resolve(task.status) != rule.final_state:
                            logger.warning("Final status not confirmed for %s", request.task_key)
                            continue
                        state = "completed"
                if await self.repository.set_state(request, state, task.status, now):
                    completed += state == "completed"
            except TeamStormError:
                logger.warning("Could not finalize %s; will retry", request.task_key)
        return completed

    async def run(self, stop: asyncio.Event, *, interval: float = 30) -> None:
        if interval <= 0:
            raise ValueError("Polling interval must be positive")
        while not stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass
