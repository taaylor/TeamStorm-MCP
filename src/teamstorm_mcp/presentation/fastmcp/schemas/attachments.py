from teamstorm_mcp.application.models import Attachment, TeamStormModel


class AttachmentsResult(TeamStormModel):
    task_key: str
    attachments: list[Attachment]
