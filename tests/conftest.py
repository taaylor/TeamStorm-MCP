from collections.abc import Iterator
from functools import partial
from unittest.mock import Mock

import aiohttp
import pytest
from aioresponses import aioresponses


@pytest.fixture
def http_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[aioresponses]:
    # aioresponses 0.7.9 omits the stream_writer argument required by aiohttp 3.14.
    monkeypatch.setattr(
        "aioresponses.core.ClientResponse",
        partial(aiohttp.ClientResponse, stream_writer=Mock(output_size=0)),
    )
    with aioresponses() as mock:
        yield mock
