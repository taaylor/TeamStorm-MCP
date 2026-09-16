from fastmcp import Context, FastMCP

from teamstorm_mcp.application.models import (
    Comment,
)
from teamstorm_mcp.presentation.fastmcp.constants import (
    COMPLETION_COMMENT_TOOL_DESCRIPTION,
    READ_ONLY_TOOL_ANNOTATIONS,
    WRITE_NON_IDEMPOTENT_TOOL_ANNOTATIONS,
)
from teamstorm_mcp.presentation.fastmcp.dependencies import service_from_context, tool_call
from teamstorm_mcp.presentation.fastmcp.schemas.comments import CommentsResult


def register_comments_tools(mcp: FastMCP) -> None:
    """Register TeamStorm comments tools."""

    @mcp.tool(
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
        description="Retrieve all comments for a TeamStorm task in chronological order.",
    )
    async def teamstorm_get_comments(task_key: str, ctx: Context) -> CommentsResult:
        comments = await tool_call(service_from_context(ctx).get_comments(task_key))
        return CommentsResult(task_key=task_key.strip().upper(), comments=comments)

    @mcp.tool(
        annotations=WRITE_NON_IDEMPOTENT_TOOL_ANNOTATIONS,
        description=COMPLETION_COMMENT_TOOL_DESCRIPTION,
    )
    async def teamstorm_add_comment(
        task_key: str,
        text: str,
        ctx: Context,
    ) -> Comment:
        return await tool_call(service_from_context(ctx).add_comment(task_key, text))
