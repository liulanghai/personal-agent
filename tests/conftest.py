"""Shared test configuration.

Tests must never reach real networks or paid model APIs. Fake providers and
httpx.MockTransport bypass the real transport, so any request that does hit
it is a bug in the test setup.
"""

from typing import NoReturn

import httpx
import pytest


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> NoReturn:
        pytest.fail(f"Real network/model calls are not allowed in tests: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)
