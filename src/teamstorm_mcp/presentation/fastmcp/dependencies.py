from collections.abc import Awaitable

from fastmcp import Context
from fastmcp.exceptions import ToolError

from teamstorm_mcp.application.exceptions import TeamStormError
from teamstorm_mcp.application.services.teamstorm import TeamStormService


def service_from_context(ctx: Context) -> TeamStormService:
    context = ctx.lifespan_context
    if not isinstance(context, dict):
        raise RuntimeError("FastMCP lifespan context is not initialized.")
    service = context.get("service")
    if not isinstance(service, TeamStormService):
        raise RuntimeError("TeamStorm service is not initialized.")
    return service


async def tool_call[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except TeamStormError as exc:
        raise ToolError(str(exc)) from exc
