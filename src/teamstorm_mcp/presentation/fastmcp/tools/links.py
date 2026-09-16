from fastmcp import Context, FastMCP

from teamstorm_mcp.presentation.fastmcp.constants import (
    READ_ONLY_TOOL_ANNOTATIONS,
)
from teamstorm_mcp.presentation.fastmcp.dependencies import service_from_context, tool_call
from teamstorm_mcp.presentation.fastmcp.schemas.links import LinksResult


def register_links_tools(mcp: FastMCP) -> None:
    """Register TeamStorm links tools."""

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description=(
            "Retrieve directly related TeamStorm tasks without recursively loading their links."
        ),
    )
    async def teamstorm_get_links(task_key: str, ctx: Context) -> LinksResult:
        links = await tool_call(service_from_context(ctx).get_links(task_key))
        return LinksResult(task_key=task_key.strip().upper(), links=links)
