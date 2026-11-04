"""Runs: listing, details, context manifest, cancellation and the SSE event stream."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...store import ACTIVE_STATUSES, RunRow
from .. import schemas as api
from ..deps import Services, require_run

POLL_SECONDS = 0.25
KEEPALIVE_TICKS = 40  # ~10s at POLL_SECONDS


def build(services: Services) -> APIRouter:
    router = APIRouter()
    store, runtime = services.store, services.runtime

    @router.get("/runs", response_model=api.Runs)
    async def runs(conversation_id: str | None = None) -> dict[str, Any]:
        return {"items": store.list_runs(conversation_id)}

    @router.get("/runs/{rid}/model-calls", response_model=api.ModelCalls)
    async def model_calls(rid: str) -> dict[str, Any]:
        require_run(store, rid)
        return {"items": store.list_model_calls(rid)}

    @router.get("/runs/{rid}/context", response_model=api.ContextManifest)
    async def run_context(rid: str) -> Any:
        require_run(store, rid)
        manifest = store.latest_event_data(rid, "context.built")
        if manifest is None:
            raise HTTPException(404, "此任务暂无上下文记录")
        return manifest

    @router.get("/runs/{rid}", response_model=api.Run)
    async def run(rid: str) -> RunRow:
        return require_run(store, rid)

    @router.post("/runs/{rid}/cancel", response_model=api.Run)
    async def cancel(rid: str) -> RunRow:
        if require_run(store, rid)["status"] in ACTIVE_STATUSES:
            await runtime.cancel(rid)
        return require_run(store, rid)

    @router.get("/runs/{rid}/events")
    async def events(
        rid: str,
        request: Request,
        after: int = 0,
        last_event_id: str | None = Header(default=None),
    ) -> StreamingResponse:
        require_run(store, rid)
        if last_event_id:
            sequence = store.event_sequence(rid, last_event_id)
            if sequence is None:
                raise HTTPException(400, "Invalid event cursor")
            after = sequence

        async def stream() -> AsyncIterator[str]:
            cursor = after
            ticks = 0
            while not await request.is_disconnected():
                batch = store.events(rid, cursor)
                for event in batch:
                    data = json.dumps(event, ensure_ascii=False)
                    yield "id: " + event["id"] + "\ndata: " + data + "\n\n"
                    cursor = event["sequence"]
                current = store.get_run(rid)
                if not batch and (current is None or current["status"] not in ACTIVE_STATUSES):
                    break
                ticks += 1
                if ticks % KEEPALIVE_TICKS == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(POLL_SECONDS)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
