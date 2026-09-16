"""Render the canonical TeamStorm task description."""

from html import escape

from teamstorm_mcp.application.constants import (
    TASK_SUMMARY_HEADING,
    WORK_DONE_HEADING,
    WORK_DONE_PLACEHOLDER,
)
from teamstorm_mcp.application.exceptions import TeamStormBadRequestError


def render_task_description(task_summary: str, work_done: list[str] | None = None) -> str:
    """Build supported TeamStorm HTML from plain-text description sections."""

    summary = task_summary.strip()
    if not summary:
        raise TeamStormBadRequestError("Task summary must not be empty.")

    completed_items = _normalize_work_done(work_done)
    sections = [
        f"<h2>{TASK_SUMMARY_HEADING}</h2>",
        _render_paragraphs(summary),
        "<hr>",
        f"<h2>{WORK_DONE_HEADING}</h2>",
        _render_work_done(completed_items),
    ]
    return "\n".join(sections)


def _render_paragraphs(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [" ".join(block.split()) for block in normalized.split("\n\n") if block.strip()]
    return "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)


def _normalize_work_done(work_done: list[str] | None) -> list[str]:
    if work_done is None:
        return []

    normalized: list[str] = []
    for item in work_done:
        value = " ".join(item.split())
        if not value:
            raise TeamStormBadRequestError("Work done items must not be empty.")
        normalized.append(value)
    return normalized


def _render_work_done(items: list[str]) -> str:
    if not items:
        return f"<p>{WORK_DONE_PLACEHOLDER}</p>"

    rendered_items = "\n".join(f"<li>{escape(item)}</li>" for item in items)
    return f"<ul>\n{rendered_items}\n</ul>"
