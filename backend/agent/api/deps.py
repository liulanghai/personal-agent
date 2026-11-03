"""Shared services passed to route factories, plus lookup helpers that 404."""

from dataclasses import dataclass

from ..config import SettingsStore
from ..runtime.runtime import Runtime
from ..store import ConversationRow, FileRow, RunRow, Store
from ..tools.registry import Tools
from .errors import not_found


@dataclass(frozen=True)
class Services:
    store: Store
    tools: Tools
    settings: SettingsStore
    runtime: Runtime


def require_conversation(store: Store, conversation_id: str) -> ConversationRow:
    row = store.get_conversation(conversation_id)
    if row is None:
        raise not_found()
    return row


def require_run(store: Store, run_id: str) -> RunRow:
    row = store.get_run(run_id)
    if row is None:
        raise not_found()
    return row


def require_file(store: Store, file_id: str) -> FileRow:
    row = store.get_file(file_id)
    if row is None:
        raise not_found()
    return row
