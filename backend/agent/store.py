"""SQLite is the authoritative store; events are replayable independently of clients."""

import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4


def uid(prefix):
    return prefix + "_" + uuid4().hex


def now():
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
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
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            db.execute(sql, args)

    def event(self, run_id, kind, data):
        event_id = uid("evt")
        self.execute(
            "INSERT INTO events(id,run_id,type,data,created_at) VALUES (?,?,?,?,?)",
            (event_id, run_id, kind, json.dumps(data, ensure_ascii=False), now()),
        )

    def events(self, run_id, after=0):
        rows = self.rows(
            "SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 200",
            (run_id, after),
        )
        for row in rows:
            row["data"] = json.loads(row["data"])
        return rows

    def status(self, run_id, status, error=None):
        self.execute(
            "UPDATE runs SET status=?,error=?,updated_at=? WHERE id=?",
            (status, error, now(), run_id),
        )
