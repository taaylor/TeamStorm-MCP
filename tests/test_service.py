from unittest.mock import AsyncMock

import pytest

from teamstorm_mcp.client import TeamStormClient
from teamstorm_mcp.exceptions import TeamStormConnectionError
from teamstorm_mcp.models import Attachment, Comment, WorkItem, WorkItemAttribute, WorkItemLink
from teamstorm_mcp.service import TeamStormService


def task() -> WorkItem:
    return WorkItem.model_validate(
        {
            "id": "task-1",
            "key": "TS-13",
            "name": "Implement MCP",
            "attributes": [
                {
                    "id": "embedded-attribute",
                    "name": "Embedded",
                    "type": "UniString",
                    "value": "fallback",
                }
            ],
        }
    )


def attribute() -> WorkItemAttribute:
    return WorkItemAttribute.model_validate(
        {
            "id": "attribute-1",
            "name": "Acceptance Criteria",
            "description": "Definition",
            "type": "UniString",
            "value": "All checks pass",
        }
    )


def comment() -> Comment:
    return Comment.model_validate(
        {"id": "comment-1", "text": "Discussion", "createdAt": "2026-09-16T10:00:00Z"}
    )


def attachment() -> Attachment:
    return Attachment.model_validate(
        {"attachmentId": "attachment-1", "fileId": "file-1", "name": "spec.pdf"}
    )


def link() -> WorkItemLink:
    return WorkItemLink.model_validate(
        {
            "id": "link-1",
            "type": {"id": "type-1", "name": "Relates"},
            "linkedWorkitem": {"id": "task-2", "key": "TS-12", "name": "Related"},
        }
    )


@pytest.fixture
def api() -> AsyncMock:
    client = AsyncMock(spec=TeamStormClient)
    client.get_workitem.return_value = task()
    client.get_workitem_attributes.return_value = [attribute()]
    client.get_comments.return_value = [comment()]
    client.get_attachments.return_value = [attachment()]
    client.get_links.return_value = [link()]
    client.get_children.return_value = [WorkItem(id="task-3", key="TS-14", name="Child")]
    return client


async def test_get_task_context_aggregates_all_sections(api: AsyncMock) -> None:
    service = TeamStormService(api)

    context = await service.get_task_context(" ts-13 ", include_children=True)

    assert context.key == "TS-13"
    assert context.workspace == "TS"
    assert context.task.name == "Implement MCP"
    assert context.attributes[0].name == "Acceptance Criteria"
    assert context.comments[0].text == "Discussion"
    assert context.attachments[0].name == "spec.pdf"
    assert context.links[0].linked_workitem.key == "TS-12"
    assert context.children[0].key == "TS-14"
    assert context.warnings == []
    api.get_workitem.assert_awaited_once_with("TS", "TS-13")
    api.get_children.assert_awaited_once_with("TS", "TS-13")


async def test_get_task_context_skips_disabled_sections(api: AsyncMock) -> None:
    service = TeamStormService(api)

    context = await service.get_task_context(
        "TS-13",
        include_comments=False,
        include_attributes=False,
        include_attachments=False,
        include_links=False,
        include_children=False,
    )

    assert context.attributes == []
    assert context.comments == []
    assert context.attachments == []
    assert context.links == []
    assert context.children == []
    api.get_comments.assert_not_awaited()


async def test_optional_section_failure_returns_warning(api: AsyncMock) -> None:
    api.get_attachments.side_effect = TeamStormConnectionError("offline")
    service = TeamStormService(api)

    context = await service.get_task_context("TS-13")

    assert context.attachments == []
    assert context.comments
    assert context.warnings == ["Attachments could not be loaded. offline"]


async def test_attribute_failure_falls_back_to_embedded_task_attributes(api: AsyncMock) -> None:
    api.get_workitem_attributes.side_effect = TeamStormConnectionError("offline")
    service = TeamStormService(api)

    context = await service.get_task_context("TS-13")

    assert context.attributes[0].id == "embedded-attribute"
    assert context.warnings == [
        "Could not load the dedicated attributes endpoint; using task attributes."
    ]


async def test_comment_failure_is_not_silently_hidden(api: AsyncMock) -> None:
    api.get_comments.side_effect = TeamStormConnectionError("comments unavailable")
    service = TeamStormService(api)

    with pytest.raises(TeamStormConnectionError, match="comments unavailable"):
        await service.get_task_context("TS-13")


async def test_context_sections_are_bounded(api: AsyncMock) -> None:
    api.get_comments.return_value = [
        Comment(id=str(index), text=str(index), createdAt=f"2026-09-16T10:00:0{index}Z")
        for index in range(3)
    ]
    service = TeamStormService(api, max_context_items=2)

    context = await service.get_task_context("TS-13")

    assert [item.id for item in context.comments] == ["1", "2"]
    assert context.warnings == ["The comments section was truncated from 3 to 2 items."]


async def test_update_task_passes_only_typed_fields(api: AsyncMock) -> None:
    api.update_workitem.return_value = task()
    service = TeamStormService(api)

    await service.update_task("backend-42", name="New name", status="Done")

    call = api.update_workitem.await_args
    assert call.args[:2] == ("BACKEND", "BACKEND-42")
    assert call.args[2].model_dump(exclude_none=True) == {"name": "New name", "status": "Done"}


async def test_set_task_description_renders_and_updates_only_description(api: AsyncMock) -> None:
    api.update_workitem.return_value = task()
    service = TeamStormService(api)

    await service.set_task_description(
        "ts-13",
        task_summary="Add <safe> formatting",
        work_done=["Implemented renderer", "Ran tests"],
    )

    call = api.update_workitem.await_args
    assert call.args[:2] == ("TS", "TS-13")
    assert call.args[2].model_dump(exclude_none=True) == {
        "description": (
            "<h2>Суть задачи</h2>\n"
            "<p>Add &lt;safe&gt; formatting</p>\n"
            "<hr>\n"
            "<h2>Что было сделано</h2>\n"
            "<ul>\n"
            "<li>Implemented renderer</li>\n"
            "<li>Ran tests</li>\n"
            "</ul>"
        )
    }
