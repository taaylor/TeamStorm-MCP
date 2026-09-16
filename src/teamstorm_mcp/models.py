"""Pydantic API and domain models used by TeamStorm MCP."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class TeamStormModel(BaseModel):
    """Forward-compatible base model for TeamStorm API objects."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="allow",
        populate_by_name=True,
    )


class NamedReference(TeamStormModel):
    id: str
    name: str


class UserReference(TeamStormModel):
    id: str
    display_name: str
    username: str | None = None
    email: str | None = None
    provider_id: str | None = None


class StatusReference(NamedReference):
    category: NamedReference | None = None


class ParentReference(TeamStormModel):
    id: str
    node_type: str


class WorkspaceReference(TeamStormModel):
    id: str
    key: str
    name: str
    description: str | None = None
    author: UserReference | None = None


class PortfolioReference(TeamStormModel):
    id: str
    name: str
    elements: list[NamedReference] = Field(default_factory=list)


class WorkItemAttribute(TeamStormModel):
    id: str
    name: str
    description: str | None = None
    type: str
    value: JsonValue | None = None


class WorkItem(TeamStormModel):
    id: str
    key: str
    name: str
    description: str | None = None
    type: NamedReference | None = None
    workflow: NamedReference | None = None
    status: StatusReference | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    created_date: datetime | None = None
    due_date: datetime | None = None
    assignee: UserReference | None = None
    author: UserReference | None = None
    sprint: NamedReference | None = None
    folder: NamedReference | None = None
    original_estimate: int | None = None
    time_spent: int | None = None
    remaining_estimate: int | None = None
    story_points: float | None = None
    changed_by: UserReference | None = None
    change_date: datetime | None = None
    parent: ParentReference | None = None
    attributes: list[WorkItemAttribute] = Field(default_factory=list)
    portfolios: list[PortfolioReference] = Field(default_factory=list)
    workspace: WorkspaceReference | None = None


class Comment(TeamStormModel):
    id: str
    text: str
    author: UserReference | None = None
    created_at: datetime
    updated_at: datetime | None = None


class Attachment(TeamStormModel):
    attachment_id: str
    workspace_id: str | None = None
    created_by: UserReference | None = None
    file_id: str
    name: str
    type: str | None = None
    size: int | None = None
    created_at: datetime | None = None


class WorkItemLink(TeamStormModel):
    id: str
    type: NamedReference
    linked_workitem: WorkItem


class ItemsResponse[T](TeamStormModel):
    """TeamStorm envelope used by several list endpoints."""

    items: list[T] = Field(default_factory=list)


class PaginationResponse[T](ItemsResponse[T]):
    """Token-based TeamStorm pagination envelope."""

    from_token: str | None = None
    max_items_count: int | None = None
    next_token: str | None = None


class TaskUpdate(BaseModel):
    """Intentionally limited set of fields that MCP may update."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, min_length=1)


class TaskContext(TeamStormModel):
    key: str
    workspace: str
    task: WorkItem
    attributes: list[WorkItemAttribute] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    links: list[WorkItemLink] = Field(default_factory=list)
    children: list[WorkItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CommentsResult(TeamStormModel):
    task_key: str
    comments: list[Comment]


class AttachmentsResult(TeamStormModel):
    task_key: str
    attachments: list[Attachment]


class LinksResult(TeamStormModel):
    task_key: str
    links: list[WorkItemLink]
