"""Opt-in learning records, separate from run events and application logs."""

import json
from base64 import b64encode
from contextvars import ContextVar
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit

from ..store import Store, now

# Task-local binding keeps concurrent conversations and injected providers isolated.
recording_scope: ContextVar[tuple[Store, str, str] | None] = ContextVar(
    "model_recording", default=None
)


class Recorder:
    def __init__(
        self, scope: tuple[Store, str, str], url: str, key: str, body: dict[str, Any]
    ) -> None:
        self.store, run_id, conversation_id = scope
        self.started = monotonic()
        parts = urlsplit(url)
        credentials = {key, unquote(parts.username or ""), unquote(parts.password or "")}
        credentials.update(value for _, value in parse_qsl(parts.query))
        if parts.username:
            basic = unquote(parts.username) + ":" + unquote(parts.password or "")
            credentials.add(b64encode(basic.encode()).decode())
        self.secrets = {
            variant
            for credential in credentials
            if credential
            for variant in (
                credential,
                quote(credential, safe=""),
                json.dumps(credential, ensure_ascii=True)[1:-1],
                json.dumps(credential, ensure_ascii=False)[1:-1],
            )
        }
        self.secrets |= {value.replace("/", "\\/") for value in self.secrets}
        # Credentials and every query parameter are discarded, including unknown names.
        safe_url = urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
        self.raw = ""
        self.record = self.store.create_model_call(
            run_id,
            {
                "conversation_id": conversation_id,
                "url": self.clean(unquote(safe_url)),
                "method": "POST",
                "model": self.clean(body["model"]),
                "started_at": now(),
                "finished_at": None,
                "duration_ms": 0,
                "http_status": None,
                "status": "running",
                "request": self.clean(body),
                "response": {"content": "", "tool_calls": [], "usage": None},
                "raw_response": "",
                "error": None,
            },
        )

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in sorted(self.secrets, key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
                # JSON responses may echo credentials with escaped characters.
                escaped = json.dumps(secret, ensure_ascii=True)[1:-1]
                value = value.replace(escaped, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {self.clean(k): self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        return value

    def save(self, *, final: bool = False) -> None:
        raw = self.clean(self.raw)
        # Hold the longest possible credential prefix across chunk boundaries.
        # On cancellation/failure it must stay redacted, never be flushed as plaintext.
        variants = self.secrets | {json.dumps(s, ensure_ascii=True)[1:-1] for s in self.secrets}
        withheld = max(
            (
                length
                for secret in variants
                for length in range(1, len(secret))
                if raw.endswith(secret[:length])
            ),
            default=0,
        )
        if withheld:
            raw = raw[:-withheld] + ("[REDACTED]" if final else "")
        self.record["raw_response"] = raw
        self.record["duration_ms"] = round((monotonic() - self.started) * 1000)
        # Redact untrusted payloads, preserving internal field names and lookup IDs.
        self.store.save_model_call(
            {
                **self.record,
                "response": self.clean(self.record["response"]),
                "error": self.clean(self.record["error"]),
            }
        )

    def receive(self, text: str) -> None:
        self.raw += text
        self.save()

    def finish(self, status: str, error: str | None = None) -> None:
        self.record.update(status=status, error=error, finished_at=now())
        self.save(final=True)
