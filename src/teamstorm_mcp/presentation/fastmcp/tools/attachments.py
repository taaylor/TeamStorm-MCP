from fastmcp import Context, FastMCP

from teamstorm_mcp.presentation.fastmcp.constants import (
    READ_ONLY_TOOL_ANNOTATIONS,
)
from teamstorm_mcp.presentation.fastmcp.dependencies import service_from_context, tool_call
from teamstorm_mcp.presentation.fastmcp.schemas.attachments import AttachmentsResult


def register_attachments_tools(mcp: FastMCP) -> None:
    """Register TeamStorm attachments tools."""

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description="Retrieve attachment metadata for a TeamStorm task without downloading files.",
    )
    async def teamstorm_get_attachments(
        task_key: str,
        ctx: Context,
    ) -> AttachmentsResult:
        attachments = await tool_call(service_from_context(ctx).get_attachments(task_key))
        return AttachmentsResult(task_key=task_key.strip().upper(), attachments=attachments)
