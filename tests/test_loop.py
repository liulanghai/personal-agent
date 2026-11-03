"""AgentLoop behavior with a scripted provider: no HTTP involved."""

import asyncio
import json
from pathlib import Path

import pytest

from agent.config import Settings
from agent.context.builder import ContextBuilder
from agent.providers.base import Finish, ProviderError, StreamEvent
from agent.runtime.loop import INVALID_ARGUMENTS, AgentLoop
from agent.store import RunRow, Store
from agent.tools.registry import Tools
from support.scripted_provider import ScriptedProvider, call, text_turn, tool_turn

SETTINGS: Settings = {
    "base_url": "https://model.example/v1",
    "model": "m",
    "api_key": "test-key",
    "timezone": "Asia/Shanghai",
    "instruction_mode": "auto",
}


class Harness:
    def __init__(self, tmp_path: Path, provider: ScriptedProvider) -> None:
        self.store = Store(tmp_path / "test.sqlite")
        tools = Tools(tmp_path / "ws", tmp_path / "bundled", self.store, home=tmp_path / "home")
        self.provider = provider
        self.loop = AgentLoop(
            self.store, tools, lambda: SETTINGS, ContextBuilder(tools), lambda _: provider
        )
        conversation = self.store.create_conversation("t")
        run_id = self.store.create_run(
            conversation_id=conversation,
            content="hi",
            skill_id=None,
            file_ids=[],
            request_key=None,
            request_hash="h",
        )
        run = self.store.get_run(run_id)
        assert run is not None
        self.run: RunRow = run

    def execute(self) -> str:
        return asyncio.run(self.loop.run(self.run, []))

    def event_types(self) -> list[str]:
        return [e["type"] for e in self.store.events(self.run["id"])]


def test_invalid_json_arguments_go_back_to_model_as_tool_error(tmp_path: Path) -> None:
    provider = ScriptedProvider([tool_turn(call("list_files", "{not json")), text_turn("done")])
    harness = Harness(tmp_path, provider)
    assert harness.execute() == "done"
    tool_message = provider.requests[1][-1]
    assert tool_message.role == "tool" and tool_message.tool_call_id == "call_list_files"
    assert json.loads(tool_message.content or "") == INVALID_ARGUMENTS
    # The tool never ran, so no tool_call events were recorded.
    assert "tool_call.started" not in harness.event_types()


def test_tool_failure_is_reported_to_model_and_run_continues(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        [tool_turn(call("read_file", {"path": "missing.md"})), text_turn("recovered")]
    )
    harness = Harness(tmp_path, provider)
    assert harness.execute() == "recovered"
    assert "error" in json.loads(provider.requests[1][-1].content or "")
    completed = [
        e for e in harness.store.events(harness.run["id"]) if e["type"] == "tool_call.completed"
    ]
    assert completed[0]["data"]["status"] == "failed"


def test_text_across_steps_is_joined_and_streamed(tmp_path: Path) -> None:
    first: list[StreamEvent] = [*text_turn("看一下")[:1], call("list_files"), Finish("tool_calls")]
    provider = ScriptedProvider([first, text_turn("好了")])
    harness = Harness(tmp_path, provider)
    assert harness.execute() == "看一下\n\n好了"
    assert harness.event_types().count("message.delta") == 2
    assert provider.requests[1][-2].content == "看一下"
    assert provider.closed


def test_step_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")
    provider = ScriptedProvider([tool_turn(call("list_files"))] * 3)
    with pytest.raises(ValueError, match="最大工具执行步数"):
        Harness(tmp_path, provider).execute()
    assert len(provider.requests) == 2


def test_empty_model_turn_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="没有返回可显示的内容"):
        Harness(tmp_path, ScriptedProvider([[Finish("stop")]])).execute()


def test_provider_error_becomes_user_facing_failure_and_closes_provider(tmp_path: Path) -> None:
    def fail(messages: object) -> list[StreamEvent]:
        raise ProviderError(
            "rate_limit", "模型服务返回 HTTP 429，请检查设置、模型权限或额度", retryable=True
        )

    provider = ScriptedProvider([fail])
    with pytest.raises(ValueError, match="HTTP 429"):
        Harness(tmp_path, provider).execute()
    assert provider.closed
