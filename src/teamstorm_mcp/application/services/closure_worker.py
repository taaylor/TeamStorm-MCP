import asyncio
import logging
from datetime import UTC, datetime

from teamstorm_mcp.application.exceptions import TeamStormError
from teamstorm_mcp.application.interfaces.task_status import TaskStatusContextProvider
from teamstorm_mcp.application.scheduling import ClosureRepository

logger = logging.getLogger(__name__)


class ClosureWorker:
    """Prepare status contexts for due tasks without changing TeamStorm statuses."""

    def __init__(
        self,
        repository: ClosureRepository,
        status_context: TaskStatusContextProvider,
    ) -> None:
        self.repository = repository
        self.status_context = status_context

    async def tick(self, now: datetime | None = None) -> int:
        checked_at = now or datetime.now(UTC)
        if checked_at.utcoffset() is None:
            raise ValueError("Worker time must include a timezone")
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

    async def run(self, stop: asyncio.Event, *, interval: float = 30) -> None:
        if interval <= 0:
            raise ValueError("Polling interval must be positive")
        while not stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass
