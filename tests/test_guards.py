"""Guards that keep the test suite hermetic."""

import asyncio

import httpx
import pytest


def test_real_network_is_blocked() -> None:
    async def fetch() -> None:
        async with httpx.AsyncClient() as client:
            await client.get("https://model.example/v1/models")

    with pytest.raises(pytest.fail.Exception, match="not allowed in tests"):
        asyncio.run(fetch())
