"""SQLite is the authoritative store; events are replayable independently of clients.

All SQL in the application lives in this module. Callers use the named methods
below and receive TypedDict rows, so the HTTP and runtime layers never build
query strings themselves.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast
from uuid import uuid4

RunStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
FileKind = Literal["upload", "artifact"]

# A conversation may have at most one run in these states (see one_active_run).
ACTIVE_STATUSES: tuple[RunStatus, ...] = ("queued", "running")


class ConversationRow(TypedDict):
    id: str
    title: str
    created_at: str


class MessageRow(TypedDict):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    run_id: str
    created_at: str


class HistoryItem(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class RunRow(TypedDict):
    id: str
    conversation_id: str
    status: RunStatus
    skill_id: str | None
    file_ids: list[str]  # stored as JSON text, decoded on read
    error: str | None
    created_at: str
    updated_at: str
    request_key: str | None
    request_hash: str


class EventRow(TypedDict):
    sequence: int
    id: str
    run_id: str
    type: str
    data: Any  # stored as JSON text, decoded on read
    created_at: str


class FileRow(TypedDict):
    id: str
    name: str
    path: str
    kind: FileKind
    run_id: str | None
    size: int
    created_at: str


class RunConflictError(Exception):
    """The conversation already has an active run, or the request key is taken."""


def uid(prefix: str) -> str:
    return prefix + "_" + uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS conversations(
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS messages(
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,
    content TEXT,
    run_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS runs(
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    status TEXT,
    skill_id TEXT,
    file_ids TEXT,
    error TEXT,
    created_at TEXT,
    updated_at TEXT,
    request_key TEXT UNIQUE,
    request_hash TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(conversation_id)
    WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE,
    run_id TEXT,
    type TEXT,
    data TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS run_events ON events(run_id, sequence);
CREATE TABLE IF NOT EXISTS files(
    id TEXT PRIMARY KEY,
    name TEXT,
    path TEXT,
    kind TEXT,
    run_id TEXT,
    size INTEGER,
    created_at TEXT
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self.connect() as db:
            db.executescript(SCHEMA)

    # -- low-level helpers ---------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        """Run one write statement. Also used by tests to seed raw rows."""
        with self.connect() as db:
            db.execute(sql, args)

    def _rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    # -- conversations and messages ------------------------------------------

    def list_conversations(self) -> list[ConversationRow]:
        rows = self._rows("SELECT * FROM conversations ORDER BY created_at DESC")
        return cast(list[ConversationRow], rows)

    def get_conversation(self, conversation_id: str) -> ConversationRow | None:
        row = self._one("SELECT * FROM conversations WHERE id=?", (conversation_id,))
        return cast(ConversationRow | None, row)

    def create_conversation(self, title: str) -> str:
        conversation_id = uid("conv")
        self.execute("INSERT INTO conversations VALUES (?,?,?)", (conversation_id, title, now()))
        return conversation_id

    def list_messages(self, conversation_id: str) -> list[MessageRow]:
        rows = self._rows(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid", (conversation_id,)
        )
        return cast(list[MessageRow], rows)

    def history(self, conversation_id: str) -> list[HistoryItem]:
        """Messages in model-history shape (role and content only)."""
        rows = self._rows(
            "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY rowid",
            (conversation_id,),
        )
        return cast(list[HistoryItem], rows)

    def add_assistant_message(self, conversation_id: str, content: str, run_id: str) -> None:
        self.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            (uid("msg"), conversation_id, "assistant", content, run_id, now()),
        )

    # -- runs -----------------------------------------------------------------

    def _run(self, row: dict[str, Any] | None) -> RunRow | None:
        if row is None:
            return None
        return cast(RunRow, {**row, "file_ids": json.loads(row["file_ids"])})

    def get_run(self, run_id: str) -> RunRow | None:
        return self._run(self._one("SELECT * FROM runs WHERE id=?", (run_id,)))

    def get_run_by_request_key(self, request_key: str) -> RunRow | None:
        return self._run(self._one("SELECT * FROM runs WHERE request_key=?", (request_key,)))

    def list_runs(self, conversation_id: str | None = None) -> list[RunRow]:
        if conversation_id:
            rows = self._rows(
                "SELECT * FROM runs WHERE conversation_id=? ORDER BY created_at DESC LIMIT 100",
                (conversation_id,),
            )
        else:
            rows = self._rows("SELECT * FROM runs ORDER BY created_at DESC LIMIT 100")
        return [cast(RunRow, self._run(row)) for row in rows]

    def list_active_run_ids(self) -> list[str]:
        rows = self._rows("SELECT id FROM runs WHERE status IN ('queued','running')")
        return [row["id"] for row in rows]

    def create_run(
        self,
        *,
        conversation_id: str,
        content: str,
        skill_id: str | None,
        file_ids: list[str],
        request_key: str | None,
        request_hash: str,
    ) -> str:
        """Atomically queue a run, record the user message and name the conversation.

        Raises RunConflictError when the conversation already has an active run
        (or, in a race, when the idempotency key was taken concurrently).
        """
        run_id, timestamp = uid("run"), now()
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        conversation_id,
                        "queued",
                        skill_id,
                        json.dumps(file_ids),
                        None,
                        timestamp,
                        timestamp,
                        request_key,
                        request_hash,
                    ),
                )
                db.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                    (uid("msg"), conversation_id, "user", content, run_id, timestamp),
                )
                db.execute(
                    "UPDATE conversations SET title=? WHERE id=? AND title='新对话'",
                    (content[:32], conversation_id),
                )
        except sqlite3.IntegrityError:
            raise RunConflictError(conversation_id) from None
        return run_id

    def set_run_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        self.execute(
            "UPDATE runs SET status=?,error=?,updated_at=? WHERE id=?",
            (status, error, now(), run_id),
        )

    # -- events ---------------------------------------------------------------

    def add_event(self, run_id: str, kind: str, data: Any) -> None:
        event_id = uid("evt")
        self.execute(
            "INSERT INTO events(id,run_id,type,data,created_at) VALUES (?,?,?,?,?)",
            (event_id, run_id, kind, json.dumps(data, ensure_ascii=False), now()),
        )

    def events(self, run_id: str, after: int = 0) -> list[EventRow]:
        rows = self._rows(
            "SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 200",
            (run_id, after),
        )
        for row in rows:
            row["data"] = json.loads(row["data"])
        return cast(list[EventRow], rows)

    def event_sequence(self, run_id: str, event_id: str) -> int | None:
        row = self._one("SELECT sequence FROM events WHERE id=? AND run_id=?", (event_id, run_id))
        return None if row is None else int(row["sequence"])

    def latest_event_data(self, run_id: str, kind: str) -> Any | None:
        row = self._one(
            "SELECT data FROM events WHERE run_id=? AND type=? ORDER BY sequence DESC LIMIT 1",
            (run_id, kind),
        )
        return None if row is None else json.loads(row["data"])

    # -- files ----------------------------------------------------------------

    def get_file(self, file_id: str) -> FileRow | None:
        return cast(FileRow | None, self._one("SELECT * FROM files WHERE id=?", (file_id,)))

    def create_file(
        self,
        *,
        file_id: str,
        name: str,
        path: str,
        kind: FileKind,
        run_id: str | None,
        size: int,
    ) -> None:
        self.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?)",
            (file_id, name, path, kind, run_id, size, now()),
        )

    def list_artifacts(self, run_id: str | None = None) -> list[FileRow]:
        if run_id:
            rows = self._rows(
                "SELECT * FROM files WHERE kind='artifact' AND run_id=? ORDER BY created_at DESC",
                (run_id,),
            )
        else:
            rows = self._rows(
                "SELECT * FROM files WHERE kind='artifact' ORDER BY created_at DESC LIMIT 100"
            )
        return cast(list[FileRow], rows)
