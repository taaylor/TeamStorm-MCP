import pytest

from teamstorm_mcp.exceptions import InvalidTaskKeyError
from teamstorm_mcp.parser import TaskKey, parse_task_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TS-1", TaskKey(workspace="TS", key="TS-1")),
        ("TS-123", TaskKey(workspace="TS", key="TS-123")),
        ("backend-42", TaskKey(workspace="BACKEND", key="BACKEND-42")),
        ("BACKEND-42", TaskKey(workspace="BACKEND", key="BACKEND-42")),
        ("ABC123-999", TaskKey(workspace="ABC123", key="ABC123-999")),
        ("  ts-13  ", TaskKey(workspace="TS", key="TS-13")),
    ],
)
def test_parse_task_key(raw: str, expected: TaskKey) -> None:
    assert parse_task_key(raw) == expected


@pytest.mark.parametrize("raw", ["invalid", "TS", "TS-", "-123", "1TS-2", "TS_1"])
def test_parse_task_key_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(InvalidTaskKeyError, match="Expected a value like TS-123"):
        parse_task_key(raw)
