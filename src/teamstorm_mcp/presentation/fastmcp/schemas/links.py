from teamstorm_mcp.application.models import TeamStormModel, WorkItemLink


class LinksResult(TeamStormModel):
    task_key: str
    links: list[WorkItemLink]
