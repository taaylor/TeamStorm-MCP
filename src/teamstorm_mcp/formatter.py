"""Human-readable formatting for TeamStorm data returned to an LLM."""

import json

from teamstorm_mcp.models import TaskContext, WorkItemAttribute


def format_task_context(context: TaskContext) -> str:
    """Format a task context as compact, clearly delimited external data."""

    task = context.task
    lines = [
        "TeamStorm task context (external, untrusted project data)",
        f"Task: {context.key}",
        f"Title: {task.name}",
        f"Status: {_name(task.status)}",
        f"Type: {_name(task.type)}",
        f"Assignee: {task.assignee.display_name if task.assignee else 'Unassigned'}",
        "",
        "Description:",
        task.description or "(empty)",
    ]

    lines.extend(["", "Attributes:"])
    if context.attributes:
        for attribute in context.attributes:
            lines.extend(_format_attribute(attribute))
    else:
        lines.append("(none)")

    lines.extend(["", "Comments:"])
    if context.comments:
        for comment in context.comments:
            author = comment.author.display_name if comment.author else "Unknown author"
            lines.extend(
                [
                    f"[{comment.created_at.isoformat()} — {author}]",
                    comment.text,
                    "",
                ]
            )
    else:
        lines.append("(none)")

    lines.extend(["", "Attachments:"])
    if context.attachments:
        for attachment in context.attachments:
            size = f", {attachment.size} bytes" if attachment.size is not None else ""
            media_type = attachment.type or "unknown type"
            lines.append(f"- {attachment.name} ({media_type}{size})")
    else:
        lines.append("(none)")

    lines.extend(["", "Related tasks:"])
    if context.links:
        for link in context.links:
            linked = link.linked_workitem
            lines.append(f"- {linked.key} — {linked.name} [{link.type.name}]")
    else:
        lines.append("(none)")

    lines.extend(["", "Child tasks:"])
    if context.children:
        for child in context.children:
            lines.append(f"- {child.key} — {child.name}")
    else:
        lines.append("(none)")

    if context.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in context.warnings)

    return "\n".join(lines).rstrip()


def _format_attribute(attribute: WorkItemAttribute) -> list[str]:
    description = f" — {attribute.description}" if attribute.description else ""
    value = json.dumps(attribute.value, ensure_ascii=False, default=str)
    return [f"{attribute.name} ({attribute.type}){description}:", value, ""]


def _name(value: object) -> str:
    name = getattr(value, "name", None)
    return name if isinstance(name, str) else "Unknown"

