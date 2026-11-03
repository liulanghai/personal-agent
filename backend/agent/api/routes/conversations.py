"""Conversations, their messages, and sending a message (which queues a run)."""

import hashlib
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ...store import ConversationRow, RunConflictError, RunRow
from .. import schemas as api
from ..deps import Services, require_conversation, require_file, require_run


def build(services: Services) -> APIRouter:
    router = APIRouter()
    store, tools = services.store, services.tools

    @router.get("/conversations", response_model=api.Conversations)
    async def conversations() -> dict[str, Any]:
        return {"items": store.list_conversations()}

    @router.post("/conversations", status_code=201, response_model=api.Conversation)
    async def create_conversation(body: api.ConversationInput) -> ConversationRow:
        return require_conversation(store, store.create_conversation(body.title))

    @router.get("/conversations/{cid}/messages", response_model=api.Messages)
    async def messages(cid: str) -> dict[str, Any]:
        require_conversation(store, cid)
        return {"items": store.list_messages(cid)}

    @router.post("/conversations/{cid}/messages", status_code=202, response_model=api.Run)
    async def send_message(
        cid: str,
        body: api.MessageInput,
        idempotency_key: str | None = Header(default=None, max_length=200),
    ) -> RunRow:
        require_conversation(store, cid)
        digest = hashlib.sha256((cid + body.model_dump_json()).encode()).hexdigest()
        if idempotency_key:
            previous = store.get_run_by_request_key(idempotency_key)
            if previous:
                if previous["request_hash"] != digest:
                    raise HTTPException(409, "Idempotency key reused with different input")
                return previous
        if not body.content.strip():
            raise HTTPException(422, "Message must not be blank")
        if body.skill_id and body.skill_id not in [s["id"] for s in tools.skills()]:
            raise HTTPException(422, "Unknown skill")
        for file_id in body.file_ids:
            if require_file(store, file_id)["kind"] != "upload":
                raise HTTPException(422, "Only uploaded source files can be attached")
        try:
            rid = store.create_run(
                conversation_id=cid,
                content=body.content,
                skill_id=body.skill_id,
                file_ids=body.file_ids,
                request_key=idempotency_key,
                request_hash=digest,
            )
        except RunConflictError:
            raise HTTPException(409, "Conversation already has an active run") from None
        services.runtime.launch(rid)
        return require_run(store, rid)

    return router
