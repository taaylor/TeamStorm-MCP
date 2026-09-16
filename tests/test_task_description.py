import pytest

from teamstorm_mcp.exceptions import TeamStormBadRequestError
from teamstorm_mcp.task_description import render_task_description


@pytest.mark.parametrize("work_done", [None, []])
def test_render_task_description_uses_placeholder_when_work_is_not_described(
    work_done: list[str] | None,
) -> None:
    result = render_task_description("First paragraph.\n\nSecond paragraph.", work_done)

    assert result == (
        "<h2>Суть задачи</h2>\n"
        "<p>First paragraph.</p>\n"
        "<p>Second paragraph.</p>\n"
        "<hr>\n"
        "<h2>Что было сделано</h2>\n"
        "<p>Работы ещё не описаны.</p>"
    )


def test_render_task_description_escapes_all_user_content() -> None:
    result = render_task_description(
        '<script>alert("summary")</script>',
        ["Fixed <b>markup</b> & tests"],
    )

    assert "<script>" not in result
    assert "<b>" not in result
    assert "&lt;script&gt;alert(&quot;summary&quot;)&lt;/script&gt;" in result
    assert "<li>Fixed &lt;b&gt;markup&lt;/b&gt; &amp; tests</li>" in result


@pytest.mark.parametrize("task_summary", ["", "   ", "\n\t"])
def test_render_task_description_rejects_empty_summary(task_summary: str) -> None:
    with pytest.raises(TeamStormBadRequestError, match="summary must not be empty"):
        render_task_description(task_summary)


def test_render_task_description_rejects_empty_work_item() -> None:
    with pytest.raises(TeamStormBadRequestError, match="items must not be empty"):
        render_task_description("Summary", ["Implemented", "  "])
