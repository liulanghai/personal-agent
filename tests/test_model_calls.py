"""Persist actual HTTP interactions without network access or credentials."""

import asyncio
import json
from contextlib import aclosing
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.app import create_app
from agent.providers.base import Message, ProviderError
from agent.providers.openai_chat import OpenAIChatProvider
from agent.providers.recording import recording_scope
from agent.store import Store
from test_api import wait


def frame(content: str) -> bytes:
    return (
        "data: " + json.dumps({"choices": [{"delta": {"content": content}}]}) + "\r\n\r\n"
    ).encode()


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], ending: str = "done") -> None:
        self.chunks = chunks
        self.ending = ending
        self.waiting = asyncio.Event()

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.ending == "network":
            raise httpx.ReadError("test-key must never reach error records")
        if self.ending == "wait":
            self.waiting.set()
            await asyncio.Event().wait()


@pytest.mark.parametrize("ending", ["done", "network", "wait", "malformed"])
def test_partial_stream_survives_failure_cancel_and_reopen(tmp_path: Path, ending: str) -> None:
    store = Store(tmp_path / "records.db")
    raw = frame("已接收文件正文")
    chunks = [raw]
    if ending == "malformed":
        chunks.append(b"data: invalid JSON\n\n")
    stream = Chunks(chunks, ending)

    async def run() -> None:
        provider = OpenAIChatProvider(
            base_url="https://model.example/v1",
            api_key="test-key",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
        )

        async def consume() -> None:
            token = recording_scope.set((store, "run", "conversation"))
            try:
                async with aclosing(
                    provider.stream([Message(role="user", content="hi")], [], model="m")
                ) as events:
                    async for _ in events:
                        pass
            finally:
                recording_scope.reset(token)
                await provider.aclose()

        task = asyncio.create_task(consume())
        if ending == "wait":
            await stream.waiting.wait()
            saved = Store(tmp_path / "records.db").list_model_calls("run")[0]
            assert saved["raw_response"] == raw.decode()
            assert saved["response"]["content"] == "已接收文件正文"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif ending in ("network", "malformed"):
            with pytest.raises(ProviderError):
                await task
        else:
            await task

    asyncio.run(run())
    record = Store(tmp_path / "records.db").list_model_calls("run")[0]
    expected = {"done": "completed", "wait": "cancelled"}.get(ending, "failed")
    assert record["status"] == expected
    assert record["response"]["content"] == "已接收文件正文"
    assert record["raw_response"].startswith(raw.decode())
    assert record["finished_at"] and record["duration_ms"] >= 0
    assert "test-key" not in json.dumps(record)


def test_redaction_of_request_url_error_and_split_raw_chunks(tmp_path: Path) -> None:
    store = Store(tmp_path / "records.db")
    stream = Chunks([b'{"error":"test-', b'key", "detail":"test-key"}'])
    snapshots: list[str] = []
    original_save = store.save_model_call

    def observe(record: dict[str, Any]) -> None:
        snapshots.append(json.dumps(record))
        original_save(record)

    store.save_model_call = observe  # type: ignore[method-assign]

    async def run() -> None:
        token = recording_scope.set((store, "run", "conv"))
        provider = OpenAIChatProvider(
            base_url="https://user:password@model.example/test-key/v1?api_key=test-key#secret",
            api_key="test-key",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    401,
                    headers={"Authorization": "Bearer test-key", "x-api-key": "test-key"},
                    stream=stream,
                )
            ),
        )
        try:
            with pytest.raises(ProviderError):
                async for _ in provider.stream(
                    [Message(role="user", content="file test-key")], [], model="m"
                ):
                    pass
        finally:
            recording_scope.reset(token)
            await provider.aclose()

    asyncio.run(run())
    record = store.list_model_calls("run")[0]
    assert record["status"] == "failed" and record["http_status"] == 401
    assert record["url"] == "https://model.example/[REDACTED]/v1"
    assert record["raw_response"] == '{"error":"[REDACTED]", "detail":"[REDACTED]"}'
    assert "file [REDACTED]" in json.dumps(record)
    for snapshot in snapshots + [json.dumps(record)]:
        assert not any(
            secret in snapshot for secret in ("test-key", "password", "api_key=", "Authorization")
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_api_setting_http_call_order_usage_and_restart(tmp_path: Path, enabled: bool) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            data = {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c",
                                    "function": {"name": "list_files", "arguments": "{}"},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        else:
            data = {
                "choices": [{"delta": {"content": "done"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            }
        return httpx.Response(200, content="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n")

    def factory(settings):
        return OpenAIChatProvider(
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            transport=httpx.MockTransport(handler),
        )

    app = create_app(tmp_path, provider_factory=factory)
    with TestClient(app) as client:
        assert client.get("/api/v1/settings").json()["record_model_calls"] is False
        config = {
            "base_url": "https://model.example/v1",
            "model": "m",
            "api_key": "test-key",
            "record_model_calls": enabled,
        }
        assert client.put("/api/v1/settings", json=config).json()["record_model_calls"] == enabled
        # Older clients omitting the switch must preserve its saved value.
        del config["record_model_calls"]
        assert client.put("/api/v1/settings", json=config).json()["record_model_calls"] == enabled
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        run = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hi"}).json()
        rid = run["id"]
        assert wait(client, rid)["status"] == "completed"
        records = client.get(f"/api/v1/runs/{rid}/model-calls").json()["items"]
        assert len(records) == (2 if enabled else 0)
        if enabled:
            assert [r["sequence"] for r in records] == [1, 2]
            assert all(r["conversation_id"] == cid and r["run_id"] == rid for r in records)
            assert [r["request"] for r in records] == requests
            assert records[0]["response"]["tool_calls"][0]["name"] == "list_files"
            assert records[1]["response"]["usage"]["total_tokens"] == 12
        assert client.get("/api/v1/runs/missing/model-calls").status_code == 404
    # New application instance reads the same persisted calls after restart.
    with TestClient(create_app(tmp_path, provider_factory=factory)) as client:
        assert client.get(f"/api/v1/runs/{rid}/model-calls").json()["items"] == records


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_final_record_redacts_incomplete_credential_suffix(tmp_path: Path, status: str) -> None:
    from agent.providers.recording import Recorder

    store = Store(tmp_path / "calls.db")
    recorder = Recorder((store, "r", "c"), "https://example.com", "test-test", {"model": "m"})
    recorder.receive("received: test-tes")
    recorder.finish(status)
    assert store.list_model_calls("r")[0]["raw_response"] == "received: [REDACTED]"


def test_url_credentials_are_redacted_when_echoed(tmp_path: Path) -> None:
    from agent.providers.recording import Recorder

    store = Store(tmp_path / "calls.db")
    recorder = Recorder(
        (store, "r", "c"),
        "https://user:password@example.com/v1?token=query-secret",
        "test-key",
        {"model": "m"},
    )
    recorder.receive("error: password query-secret")
    recorder.finish("failed")
    record = json.dumps(store.list_model_calls("r")[0])
    assert "password" not in record and "query-secret" not in record


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [], "usage": {"prompt_tokens": "test-key"}},
        {"choices": [{"delta": {"tool_calls": [{"index": "test-key"}]}}]},
        {"error": {"message": "test-key"}},
    ],
)
def test_invalid_stream_shape_is_a_safe_provider_error(tmp_path: Path, payload: Any) -> None:
    store = Store(tmp_path / "calls.db")

    async def run() -> None:
        token = recording_scope.set((store, "r", "c"))
        provider = OpenAIChatProvider(
            base_url="https://example.com/v1",
            api_key="test-key",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, content="data: " + json.dumps(payload) + "\n\n")
            ),
        )
        try:
            with pytest.raises(ProviderError) as error:
                async for _ in provider.stream([], [], model="m"):
                    pass
            assert "test-key" not in str(error.value)
        finally:
            recording_scope.reset(token)
            await provider.aclose()

    asyncio.run(run())
    record = store.list_model_calls("r")[0]
    assert record["status"] == "failed"
    assert "test-key" not in json.dumps(record)


@pytest.mark.parametrize("key", ["status", "model"])
def test_redaction_preserves_record_schema_and_storage_identity(tmp_path: Path, key: str) -> None:
    from agent.providers.recording import Recorder

    store = Store(tmp_path / "calls.db")
    recorder = Recorder((store, "run", "conv"), "https://example.com", key, {"model": "m"})
    recorder.receive("data: received\n\n")
    recorder.finish("completed")
    record = store.list_model_calls("run")[0]
    assert record["id"] == recorder.record["id"]
    assert record["status"] == "completed"
    assert record["model"] == "m"
    assert record["raw_response"] == "data: received\n\n"


def test_concurrent_scopes_keep_calls_isolated(tmp_path: Path) -> None:
    store = Store(tmp_path / "calls.db")

    async def call(run_id: str, enabled: bool) -> None:
        token = recording_scope.set((store, run_id, run_id + "-conv") if enabled else None)
        provider = OpenAIChatProvider(
            base_url="https://example.com/v1",
            api_key="test-key",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=frame(run_id))),
        )
        try:
            await asyncio.sleep(0)
            async for _ in provider.stream([Message(role="user", content=run_id)], [], model="m"):
                await asyncio.sleep(0)
        finally:
            recording_scope.reset(token)
            await provider.aclose()

    async def run() -> None:
        await asyncio.gather(call("first", True), call("second", True), call("disabled", False))

    asyncio.run(run())
    for run_id in ("first", "second"):
        record = store.list_model_calls(run_id)[0]
        assert record["conversation_id"] == run_id + "-conv"
        assert record["response"]["content"] == run_id
        assert record["request"]["messages"][0]["content"] == run_id
        assert record["sequence"] == 1
    assert store.list_model_calls("disabled") == []
    assert recording_scope.get() is None


@pytest.mark.parametrize("newline", ["\r", "\r\n", "\n"])
def test_recording_preserves_raw_newlines_while_parsing(tmp_path: Path, newline: str) -> None:
    store = Store(tmp_path / "calls.db")
    raw = frame("正文").decode().replace("\r\n", newline) + "data: [DONE]" + newline * 2
    # Split every byte, including UTF-8 codepoints and CRLF boundaries.
    stream = Chunks([bytes([value]) for value in raw.encode()])

    async def run() -> None:
        token = recording_scope.set((store, "r", "c"))
        provider = OpenAIChatProvider(
            base_url="https://example.com/v1",
            api_key="test-key",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
        )
        try:
            async for _ in provider.stream([], [], model="m"):
                pass
        finally:
            recording_scope.reset(token)
            await provider.aclose()

    asyncio.run(run())
    record = store.list_model_calls("r")[0]
    # Parsing stops at DONE; bytes after it may not have been consumed yet.
    assert raw.startswith(record["raw_response"])
    assert "data: [DONE]" in record["raw_response"]
    assert record["response"]["content"] == "正文"
    assert record["response"]["finish_reason"] == "stop"


def test_restart_marks_unfinished_call_without_losing_data(tmp_path: Path) -> None:
    from agent.providers.recording import Recorder

    store = Store(tmp_path / "calls.db")
    recorder = Recorder((store, "r", "c"), "https://example.com", "test-key", {"model": "m"})
    recorder.receive("data: received\n\n")
    reopened = Store(tmp_path / "calls.db")
    reopened.interrupt_model_calls()
    record = reopened.list_model_calls("r")[0]
    assert record["status"] == "interrupted"
    assert record["raw_response"] == "data: received\n\n"
    assert record["finished_at"]
