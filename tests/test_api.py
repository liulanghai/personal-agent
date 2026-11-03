import json
import time
from collections.abc import Sequence

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.app import create_app
from agent.providers.base import Message, StreamEvent
from agent.providers.openai_chat import OpenAIChatProvider
from agent.tools.registry import DEFINITIONS
from support.scripted_provider import ScriptedProviderFactory, call, text_turn, tool_turn


def weekly_report_agent(messages: Sequence[Message]) -> Sequence[StreamEvent]:
    """A fake model that reacts to tool results, like a real one would.

    Loads the skill, lists files, and if an upload exists reads it and writes
    its content into a report. It never inspects the system prompt.
    """
    results = [json.loads(m.content or "null") for m in messages if m.role == "tool"]
    plan = [call("read_skill", {"skill_id": "weekly-report"}), call("list_files")]
    if len(results) >= 2:
        uploads = [path for path in results[1] if path.startswith("uploads/")]
        if uploads:
            plan.append(call("read_file", {"path": uploads[0]}))
            text = results[2].get("content", "") if len(results) >= 3 else ""
            plan.append(call("write_file", {"path": "reports/test.md", "content": text}))
    if len(results) < len(plan):
        return tool_turn(plan[len(results)])
    return text_turn("已完成测试任务")


@pytest.fixture
def factory():
    # Delay keeps runs active long enough for cancel/idempotency tests.
    return ScriptedProviderFactory([weekly_report_agent] * 8, delay=0.05)


@pytest.fixture
def app(tmp_path, monkeypatch, factory):
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {"base_url": "https://model.example/v1", "model": "test-model", "api_key": "test-key"}
        )
    )
    app = create_app(tmp_path, provider_factory=factory)
    app.state.runtime.tools.discovery.home = tmp_path / "home"
    app.state.runtime.tools.discovery.codex_home = tmp_path / "home/.codex"
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def send(client, content="生成周报", files=None, key="request-1"):
    cid = client.post("/api/v1/conversations", json={}).json()["id"]
    body = {"content": content, "skill_id": "weekly-report", "file_ids": files or []}
    response = client.post(
        f"/api/v1/conversations/{cid}/messages", json=body, headers={"Idempotency-Key": key}
    )
    assert response.status_code == 202, response.text
    return cid, response.json(), body


def wait(client, rid):
    for _ in range(100):
        run = client.get(f"/api/v1/runs/{rid}").json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.02)
    raise AssertionError("Run did not finish")


def read_events(client, rid, headers=None):
    response = client.get(f"/api/v1/runs/{rid}/events", headers=headers or {})
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def test_file_skill_artifact_history_and_replay(client, factory):
    upload = client.post(
        "/api/v1/files",
        files={"file": ("notes.md", "已完成：API设计。风险：模型未配置。".encode())},
    )
    assert upload.status_code == 201
    cid, run, _ = send(client, files=[upload.json()["id"]])
    assert wait(client, run["id"])["status"] == "completed"
    system_prompt = factory.last.requests[0][0].content or ""
    assert upload.json()["path"] in system_prompt.split("Attached files for this request: ")[1]
    assert factory.last.models == ["test-model"] * 5
    assert factory.last.closed
    events = read_events(client, run["id"])
    names = [e["data"]["tool_name"] for e in events if e["type"] == "tool_call.started"]
    assert names == ["read_skill", "list_files", "read_file", "write_file"]
    assert events[-1]["type"] == "run.completed"
    resumed = read_events(client, run["id"], {"Last-Event-ID": events[2]["id"]})
    assert resumed == events[3:]
    artifact = client.get("/api/v1/artifacts", params={"run_id": run["id"]}).json()["items"][0]
    text = client.get(f"/api/v1/files/{artifact['id']}/content").text
    assert "已完成：API设计" in text
    assert len(client.get(f"/api/v1/conversations/{cid}/messages").json()["items"]) == 2


def test_idempotency_and_conflict(client):
    cid, run, body = send(client)
    repeat = client.post(
        f"/api/v1/conversations/{cid}/messages", json=body, headers={"Idempotency-Key": "request-1"}
    )
    assert repeat.json()["id"] == run["id"]
    body["content"] = "different"
    conflict = client.post(
        f"/api/v1/conversations/{cid}/messages", json=body, headers={"Idempotency-Key": "request-1"}
    )
    assert conflict.status_code == 409


def test_cancel(client):
    _, run, _ = send(client)
    result = client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert result.json()["status"] == "cancelled"
    assert read_events(client, run["id"])[-1]["type"] == "run.cancelled"


def test_settings_secret_not_echoed_and_host_change_requires_new_key(client, tmp_path):
    value = {"base_url": "https://example.com/v1", "model": "test", "api_key": "secret-test-value"}
    result = client.put("/api/v1/settings", json=value)
    assert result.status_code == 200
    assert result.json()["has_api_key"] is True
    assert "secret-test-value" not in result.text
    assert "secret-test-value" not in client.get("/api/v1/settings").text
    assert (tmp_path / "settings.json").stat().st_mode & 0o777 == 0o600
    value.update(base_url="https://other.example/v1", api_key=None)
    assert client.put("/api/v1/settings", json=value).status_code == 422
    value.update(api_key="")
    assert client.put("/api/v1/settings", json=value).json()["has_api_key"] is False


def test_origin_and_host_protection(client):
    assert (
        client.post(
            "/api/v1/conversations", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/settings", headers={"Host": "evil.example"}).status_code == 403


def test_bearer_auth_and_preflight(app, monkeypatch):
    monkeypatch.setenv("AGENT_API_TOKEN", "test-token")
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 401
        assert (
            client.get("/api/v1/health", headers={"Authorization": "Bearer test-token"}).status_code
            == 200
        )
        assert (
            client.options(
                "/api/v1/health",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            ).status_code
            == 200
        )


def test_file_limits_and_validation(client):
    assert client.post("/api/v1/files", files={"file": ("bad.pdf", b"%PDF")}).status_code == 422
    assert (
        client.post("/api/v1/files", files={"file": ("big.txt", b"x" * 60001)}).status_code == 413
    )
    assert client.post("/api/v1/files", files={"file": ("bad.txt", b"\xff")}).status_code == 422
    cid = client.post("/api/v1/conversations", json={}).json()["id"]
    assert (
        client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "   "}).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/conversations/{cid}/messages", json={"content": "hi", "skill_id": "../escape"}
        ).status_code
        == 422
    )


def test_workspace_boundaries(app, tmp_path):
    tools = app.state.runtime.tools
    with pytest.raises(ValueError):
        tools.execute("read_file", {"path": "../../settings.json"}, "test")
    with pytest.raises(ValueError):
        tools.execute(
            "write_file", {"path": "reports/../uploads/escape.txt", "content": "oops"}, "test"
        )
    (tools.workspace / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        tools.execute("read_file", {"path": "escape/settings.json"}, "test")
    tools.execute("write_file", {"path": "reports/test.md", "content": "first"}, "test")
    with pytest.raises(FileExistsError):
        tools.execute("write_file", {"path": "reports/test.md", "content": "second"}, "test")


def test_interrupted_run_marks_failure_after_restart(tmp_path):
    app = create_app(tmp_path)
    app.state.store.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("run_old", "conv", "running", None, "[]", None, "time", "time", None, "hash"),
    )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/v1/runs/run_old").json()["status"] == "failed"


def sse(*chunks):
    lines = ["data: " + json.dumps(chunk) for chunk in chunks] + ["data: [DONE]"]
    return httpx.Response(
        200,
        content="\n\n".join(lines) + "\n\n",
        headers={"content-type": "text/event-stream"},
    )


def openai_app(tmp_path, monkeypatch, handler):
    """App wired to the real OpenAIChatProvider over httpx.MockTransport."""
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)

    def factory(settings):
        return OpenAIChatProvider(
            base_url=settings["base_url"],
            api_key=settings.get("api_key", ""),
            transport=httpx.MockTransport(handler),
        )

    app = create_app(tmp_path, provider_factory=factory)
    app.state.runtime.tools.discovery.home = tmp_path / "home"
    app.state.runtime.tools.discovery.codex_home = tmp_path / "home/.codex"
    return app


def test_compatible_model_stream_and_tool_execution(tmp_path, monkeypatch):
    calls = []

    def mock(request):
        body = json.loads(request.content)
        calls.append((request, body))
        if len(calls) == 1:
            # Arguments split across chunks, as real providers stream them.
            first = {"index": 0, "id": "call_mock", "function": {"name": "list_skills"}}
            second = {"index": 0, "function": {"arguments": "{}"}}
            return sse(
                {"choices": [{"delta": {"tool_calls": [first]}}]},
                {"choices": [{"delta": {"tool_calls": [second]}}]},
            )
        assert body["messages"][-1]["role"] == "tool"
        assert body["messages"][-1]["tool_call_id"] == "call_mock"
        assert body["messages"][-2]["tool_calls"][0]["function"]["name"] == "list_skills"
        return sse({"choices": [{"delta": {"content": "真实协议模拟成功"}}]})

    with TestClient(openai_app(tmp_path, monkeypatch, mock)) as client:
        client.put(
            "/api/v1/settings",
            json={
                "mode": "compatible",
                "base_url": "https://model.example/v1",
                "model": "mock",
                "api_key": "mock-key",
            },
        )
        cid, run, _ = send(client)
        assert wait(client, run["id"])["status"] == "completed"
        assert len(calls) == 2
        request, body = calls[0]
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer mock-key"
        assert body["model"] == "mock" and body["stream"] is True
        assert body["tools"] == DEFINITIONS
        assert (
            client.get(f"/api/v1/conversations/{cid}/messages").json()["items"][-1]["content"]
            == "真实协议模拟成功"
        )


def test_provider_http_error_fails_run_without_leaking_body(tmp_path, monkeypatch):
    def mock(request):
        return httpx.Response(401, json={"error": {"message": "bad key sk-test-leak"}})

    (tmp_path / "settings.json").write_text(
        json.dumps({"base_url": "https://model.example/v1", "model": "m", "api_key": "test-key"})
    )
    with TestClient(openai_app(tmp_path, monkeypatch, mock)) as client:
        _, run, _ = send(client)
        result = wait(client, run["id"])
        assert result["status"] == "failed"
        assert result["error"] == "模型服务返回 HTTP 401，请检查设置、模型权限或额度"
        assert "sk-test-leak" not in json.dumps(read_events(client, run["id"]))


def test_legacy_mode_is_ignored_and_configuration_is_preserved(tmp_path):
    config = {
        "mode": "demo",
        "base_url": "https://model.example/v1",
        "model": "existing-model",
        "api_key": "existing-secret",
    }
    (tmp_path / "settings.json").write_text(json.dumps(config))
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/v1/settings").json()
        assert "mode" not in response
        assert response["model"] == "existing-model" and response["has_api_key"]
        assert json.loads((tmp_path / "settings.json").read_text()) == config
        assert "mode" not in client.get("/api/v1/health").json()


def test_missing_key_fails_without_fallback(client):
    client.put(
        "/api/v1/settings",
        json={"base_url": "https://model.example/v1", "model": "test", "api_key": ""},
    )
    _, run, _ = send(client)
    result = wait(client, run["id"])
    assert result["status"] == "failed"
    assert "密钥" in result["error"]


def test_context_settings_manifest_and_discovery(client):
    current = client.get("/api/v1/settings").json()
    assert current["timezone"] == "Asia/Shanghai"
    assert current["instruction_mode"] == "auto"
    body = {"base_url": current["base_url"], "model": current["model"], "timezone": "invalid-zone"}
    assert client.put("/api/v1/settings", json=body).status_code == 422
    body["timezone"] = "Asia/Tokyo"
    assert client.put("/api/v1/settings", json=body).status_code == 200
    assert client.get("/api/v1/discovery").json()["skills"]
    _, run, _ = send(client)
    assert wait(client, run["id"])["status"] == "completed"
    manifest = client.get(f"/api/v1/runs/{run['id']}/context").json()
    assert manifest["sections"][0]["environment"]["timezone"] == "Asia/Tokyo"
    assert "test-key" not in json.dumps(manifest)
