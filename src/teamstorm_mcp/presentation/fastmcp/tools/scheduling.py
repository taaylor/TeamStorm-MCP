from fastmcp import Context, FastMCP
from pydantic import AwareDatetime

from teamstorm_mcp.application.scheduling import ClosureRequest, ClosureService, ScheduledClosure
from teamstorm_mcp.application.workflow import WorkflowMap
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
            "Save closure intent as soon as the user requests a timed closure. "
            "close_at must include a timezone. One schedule per task; changed inputs replace it. "
            "With a configured workflow, the daemon closes only from its trigger status when due. "
            "Without a workflow, the daemon only prepares status context."
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

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description="Read the complete configured workflow map; null means disabled.",
    )
    async def teamstorm_get_workflow(ctx: Context) -> WorkflowMap | None:
        workflow = closure_service(ctx).workflow
        return workflow.definition if workflow else None

    @mcp.tool(
        annotations=WRITE_IDEMPOTENT_TOOL_ANNOTATIONS,
        description="Cancel a task's saved closure intent when requested by the user.",
    )
    async def teamstorm_cancel_task_closure(task_key: str, ctx: Context) -> ScheduledClosure | None:
        return await tool_call(closure_service(ctx).cancel(task_key))
