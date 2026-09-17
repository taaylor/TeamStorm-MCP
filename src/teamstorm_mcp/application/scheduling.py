"""Persistent scheduling contracts; a ready context is not a completed transition."""

from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, Field

from teamstorm_mcp.application.exceptions import TeamStormBadRequestError
from teamstorm_mcp.application.interfaces.task_status import TaskStatusContextProvider
from teamstorm_mcp.application.models import StatusReference
from teamstorm_mcp.application.parser import parse_task_key
from teamstorm_mcp.application.workflow import Workflow


class ClosureRequest(BaseModel):
    task_key: str
    close_at: AwareDatetime
    target_status: str = Field(min_length=1)
    workflow_id: str | None = None
    workflow_revision: int | None = None
    workflow_fingerprint: str | None = None


class ScheduledClosure(ClosureRequest):
    revision: int = 1
    state: Literal["pending", "context_ready", "waiting", "completed", "cancelled", "suspended"] = (
        "pending"
    )
    current_status: StatusReference | None = None
    checked_at: AwareDatetime | None = None


class ClosureRepository(Protocol):
    async def set_state(
        self, request: ScheduledClosure, state: str, status: StatusReference | None, now: datetime
    ) -> bool: ...

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
        self,
        repository: ClosureRepository,
        status_context: TaskStatusContextProvider,
        workflow: Workflow | None = None,
    ) -> None:
        self.repository = repository
        self.status_context = status_context
        self.workflow = workflow

    async def schedule(self, request: ClosureRequest) -> ScheduledClosure:
        key = parse_task_key(request.task_key).key
        # Check existence and access before persisting the request.
        task = await self.status_context.get_task(key)
        normalized = request.model_copy(
            update={"task_key": key, "close_at": request.close_at.astimezone(UTC)}
        )
        if self.workflow is not None:
            definition = self.workflow.definition
            definition.resolve(task.status)
            final = definition.scheduled_finalization.final_state
            if definition.resolve(request.target_status) != final:
                raise TeamStormBadRequestError("Scheduled target must be the map's final status")
            normalized = normalized.model_copy(
                update={
                    "workflow_id": definition.id,
                    "workflow_revision": definition.revision,
                    "workflow_fingerprint": definition.fingerprint,
                }
            )
        result = await self.repository.schedule(normalized)
        if self.workflow is not None and result.state in {"pending", "waiting"}:
            definition = self.workflow.definition
            current = definition.resolve(task.status)
            rule = definition.scheduled_finalization
            state = "pending" if current == rule.trigger_state else "waiting"
            if current == rule.final_state:
                state = "completed"
            if result.state != state or result.current_status != task.status:
                await self.repository.set_state(result, state, task.status, datetime.now(UTC))
            return await self.repository.get(key) or result
        return result

    async def get(self, task_key: str) -> ScheduledClosure | None:
        return await self.repository.get(parse_task_key(task_key).key)

    async def cancel(self, task_key: str) -> ScheduledClosure | None:
        request = await self.get(task_key)
        if request is not None and request.state != "completed":
            if request.state != "cancelled" and not await self.repository.set_state(
                request, "cancelled", request.current_status, datetime.now(UTC)
            ):
                raise TeamStormBadRequestError("Schedule changed during cancellation; retry")
        return await self.get(task_key)
