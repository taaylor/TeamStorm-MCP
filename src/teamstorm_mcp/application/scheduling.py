"""Persistent scheduling contracts; a ready context is not a completed transition."""

from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, Field

from teamstorm_mcp.application.interfaces.task_status import TaskStatusContextProvider
from teamstorm_mcp.application.models import StatusReference
from teamstorm_mcp.application.parser import parse_task_key


class ClosureRequest(BaseModel):
    task_key: str
    close_at: AwareDatetime
    target_status: str = Field(min_length=1)


class ScheduledClosure(ClosureRequest):
    revision: int = 1
    state: Literal["pending", "context_ready"] = "pending"
    current_status: StatusReference | None = None
    checked_at: AwareDatetime | None = None


class ClosureRepository(Protocol):
    async def schedule(self, request: ClosureRequest) -> ScheduledClosure: ...

    async def get(self, task_key: str) -> ScheduledClosure | None: ...

    async def due(self, now: datetime) -> list[ScheduledClosure]: ...

    async def save_context(
        self,
        request: ScheduledClosure,
        status: StatusReference | None,
        checked_at: datetime,
    ) -> bool: ...


class ClosureService:
    def __init__(
        self, repository: ClosureRepository, status_context: TaskStatusContextProvider
    ) -> None:
        self.repository = repository
        self.status_context = status_context

    async def schedule(self, request: ClosureRequest) -> ScheduledClosure:
        key = parse_task_key(request.task_key).key
        # Check existence and access before persisting the request.
        await self.status_context.get_task(key)
        normalized = request.model_copy(
            update={"task_key": key, "close_at": request.close_at.astimezone(UTC)}
        )
        return await self.repository.schedule(normalized)

    async def get(self, task_key: str) -> ScheduledClosure | None:
        return await self.repository.get(parse_task_key(task_key).key)
