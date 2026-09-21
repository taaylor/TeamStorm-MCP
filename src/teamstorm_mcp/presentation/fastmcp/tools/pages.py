from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult

from teamstorm_mcp.presentation.fastmcp.constants import READ_ONLY_TOOL_ANNOTATIONS
from teamstorm_mcp.presentation.fastmcp.dependencies import service_from_context, tool_call
from teamstorm_mcp.presentation.fastmcp.formatter import format_task_pages


def register_pages_tools(mcp: FastMCP) -> None:
    """Register read-only TeamStorm page tools."""

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description=(
            "Retrieve documentation pages linked to a TeamStorm task across accessible workspaces. "
            "Call this tool only when the user explicitly asks for related pages or documentation. "
            "The result may include partial-loading warnings."
        ),
    )
    async def teamstorm_get_task_pages(
        task_key: str,
        ctx: Context,
        include_content: bool = True,
        max_items: int | None = None,
    ) -> ToolResult:
        result = await tool_call(
            service_from_context(ctx).get_task_pages(
                task_key,
                include_content=include_content,
                max_items=max_items,
            )
        )
        return ToolResult(
            content=format_task_pages(result),
            structured_content=result.model_dump(mode="json", by_alias=True),
        )
