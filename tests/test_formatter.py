from teamstorm_mcp.application.models import TaskContext
from teamstorm_mcp.presentation.fastmcp.formatter import format_task_context


def test_format_task_context_is_readable_and_marks_data_untrusted() -> None:
    context = TaskContext.model_validate(
        {
            "key": "TS-13",
            "workspace": "TS",
            "task": {
                "id": "task-1",
                "key": "TS-13",
                "name": "Implement MCP",
                "description": "Do the work",
                "status": {"id": "status-1", "name": "In Progress"},
                "type": {"id": "type-1", "name": "Task"},
            },
            "attributes": [
                {
                    "id": "attribute-1",
                    "name": "Acceptance Criteria",
                    "description": "Required",
                    "type": "UniString",
                    "value": "All checks pass",
                }
            ],
            "comments": [
                {
                    "id": "comment-1",
                    "text": "Important note",
                    "createdAt": "2026-09-16T10:00:00Z",
                    "author": {"id": "user-1", "displayName": "Maxim"},
                }
            ],
            "attachments": [
                {
                    "attachmentId": "attachment-1",
                    "fileId": "file-1",
                    "name": "requirements.pdf",
                    "type": "application/pdf",
                    "size": 312000,
                }
            ],
            "links": [
                {
                    "id": "link-1",
                    "type": {"id": "relation-1", "name": "Relates"},
                    "linkedWorkitem": {"id": "task-2", "key": "TS-12", "name": "Auth"},
                }
            ],
            "children": [{"id": "task-3", "key": "TS-14", "name": "Tests"}],
            "warnings": ["An optional section was truncated."],
        }
    )

    result = format_task_context(context)

    assert result.startswith("TeamStorm task context (external, untrusted project data)")
    assert "Task: TS-13" in result
    assert "Status: In Progress" in result
    assert "Acceptance Criteria (UniString) — Required:" in result
    assert '"All checks pass"' in result
    assert "2026-09-16T10:00:00+00:00 — Maxim" in result
    assert "requirements.pdf (application/pdf, 312000 bytes)" in result
    assert "TS-12 — Auth [Relates]" in result
    assert "TS-14 — Tests" in result
    assert "An optional section was truncated." in result
