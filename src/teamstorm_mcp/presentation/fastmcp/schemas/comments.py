from teamstorm_mcp.application.models import Comment, TeamStormModel


class CommentsResult(TeamStormModel):
    task_key: str
    comments: list[Comment]
