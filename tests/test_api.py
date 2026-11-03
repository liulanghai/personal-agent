import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.app import create_app

ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_API_TOKEN", raising=False)
    # Mock the provider transport; application always follows the real model loop.
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {"base_url": "https://model.example/v1", "model": "test-model", "api_key": "test-key"}
        )
    )

    async def provider(request):
        await asyncio.sleep(0.05)
        messages = json.loads(request.content)["messages"]
        files = json.loads(messages[0]["content"].split("Attached files for this request: ")[1])
        step = sum(m["role"] == "tool" for m in messages)
        plan = [("read_skill", {"skill_id": "weekly-report"}), ("list_files", {})]
        if files:
            plan.append(("read_file", {"path": files[0]["path"]}))
            text = json.loads(messages[-1]["content"]).get("content", "") if step == 3 else ""
            plan.append(("write_file", {"path": "reports/test.md", "content": text}))
        if step < len(plan):
            name, arguments = plan[step]
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_" + str(step),
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ]
            }
        else:
            delta = {"content": "已完成测试任务"}
        return httpx.Response(
            200,
            content="data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\ndata: [DONE]\n\n",
        )

    monkeypatch.setattr(
        "agent.runtime.httpx.AsyncClient",
        lambda **kwargs: ORIGINAL_ASYNC_CLIENT(transport=httpx.MockTransport(provider), **kwargs),
    )
    app = create_app(tmp_path)
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


def test_file_skill_artifact_history_and_replay(client):
    upload = client.post(
        "/api/v1/files",
        files={"file": ("notes.md", "已完成：API设计。风险：模型未配置。".encode())},
    )
    assert upload.status_code == 201
    cid, run, _ = send(client, files=[upload.json()["id"]])
    assert wait(client, run["id"])["status"] == "completed"
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


def test_compatible_model_stream_and_tool_execution(client, monkeypatch):
    calls = []
    real_client = ORIGINAL_ASYNC_CLIENT

    def mock(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_mock",
                        "function": {"name": "list_skills", "arguments": "{}"},
                    }
                ]
            }
        else:
            assert body["messages"][-1]["role"] == "tool"
            delta = {"content": "真实协议模拟成功"}
        return httpx.Response(
            200,
            content="data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n\ndata: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        "agent.runtime.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(mock), **kwargs),
    )
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
    assert (
        client.get(f"/api/v1/conversations/{cid}/messages").json()["items"][-1]["content"]
        == "真实协议模拟成功"
    )


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
