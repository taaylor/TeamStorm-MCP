from fastmcp import Context, FastMCP
from pydantic import AwareDatetime

from teamstorm_mcp.application.scheduling import ClosureRequest, ClosureService, ScheduledClosure
from teamstorm_mcp.presentation.fastmcp.constants import (
    READ_ONLY_TOOL_ANNOTATIONS,
    WRITE_IDEMPOTENT_TOOL_ANNOTATIONS,
)
from teamstorm_mcp.presentation.fastmcp.dependencies import tool_call


def closure_service(ctx: Context) -> ClosureService:
    context = ctx.lifespan_context
    if not isinstance(context, dict):
        raise RuntimeError("Closure service is not initialized")
    service = context.get("closures")
    if not isinstance(service, ClosureService):
        raise RuntimeError("Closure service is not initialized")
    return service


def register_scheduling_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=WRITE_IDEMPOTENT_TOOL_ANNOTATIONS,
        description=(
            "Schedule a status context check after work on a task is completed. "
            "Call only after finishing the work and when the user requested a scheduled closure. "
            "close_at must include a timezone. One schedule per task; changed inputs replace it. "
            "The current daemon only prepares status context; it does NOT change TeamStorm status."
        ),
    )
    async def teamstorm_schedule_task_closure(
        task_key: str, close_at: AwareDatetime, target_status: str, ctx: Context
    ) -> ScheduledClosure:
        request = ClosureRequest(task_key=task_key, close_at=close_at, target_status=target_status)
        return await tool_call(closure_service(ctx).schedule(request))

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description=(
            "Get a task's persisted closure schedule and last observed status. "
            "context_ready means the daemon read its status, NOT that the task was closed."
        ),
    )
    async def teamstorm_get_task_closure(task_key: str, ctx: Context) -> ScheduledClosure | None:
        return await tool_call(closure_service(ctx).get(task_key))
