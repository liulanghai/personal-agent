"""Agent loop: ask the model, stream text, execute tool calls, repeat.

The loop only speaks provider-neutral types (``providers.base``); HTTP, SSE and
tool-call fragment assembly belong to the provider adapter.
"""

import asyncio
import json
import os
from collections.abc import Callable
from contextlib import aclosing
from typing import Any

from ..config import Settings
from ..context.builder import ContextBuilder
from ..providers.base import (
    Message,
    Provider,
    ProviderError,
    ProviderFactory,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from ..store import FileRow, RunRow, Store, uid
from ..tools.registry import DEFINITIONS, Tools

MAX_STEPS_DEFAULT = 16
MAX_STEPS_LIMIT = 32
INVALID_ARGUMENTS = {"error": "Invalid tool arguments: expected JSON object"}


def max_steps() -> int:
    return min(int(os.getenv("AGENT_MAX_STEPS", str(MAX_STEPS_DEFAULT))), MAX_STEPS_LIMIT)


def tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name=d["function"]["name"],
            description=d["function"]["description"],
            parameters=d["function"]["parameters"],
        )
        for d in DEFINITIONS
    ]


class AgentLoop:
    def __init__(
        self,
        store: Store,
        tools: Tools,
        settings: Callable[[], Settings],
        context: ContextBuilder,
        provider_factory: ProviderFactory,
    ) -> None:
        self.store = store
        self.tools = tools
        self.settings = settings
        self.context = context
        self.provider_factory = provider_factory

    async def call_tool(self, run_id: str, name: str, args: Any) -> Any:
        """Execute one tool call, recording started/completed events.

        Tool failures are returned to the model as ``{"error": ...}`` rather than
        failing the run.
        """
        call_id = uid("call")
        self.store.add_event(
            run_id,
            "tool_call.started",
            {"tool_call_id": call_id, "tool_name": name, "arguments": args},
        )
        await asyncio.sleep(0)
        status = "succeeded"
        try:
            result = self.tools.execute(name, args, run_id)
        except Exception as exc:
            status = "failed"
            result = {"error": str(exc)[:500]}
        self.store.add_event(
            run_id,
            "tool_call.completed",
            {"tool_call_id": call_id, "tool_name": name, "status": status, "result": result},
        )
        return result

    async def run(self, run: RunRow, files: list[FileRow]) -> str:
        """Run the loop to completion and return the final assistant text."""
        # Settings are read once per run; a run never switches provider midway.
        config = self.settings()
        if not config.get("api_key") or not config.get("model"):
            raise ValueError("请先在设置中配置模型名称和 API 密钥")
        history = self.store.history(run["conversation_id"])
        messages, manifest = self.context.build(config, dict(run), files, history)
        self.store.add_event(run["id"], "context.built", manifest)
        provider = self.provider_factory(config)
        try:
            return await self._steps(provider, config["model"], run["id"], messages)
        except ProviderError as exc:
            # Provider messages are user-facing and never contain response bodies.
            raise ValueError(str(exc)) from exc
        finally:
            await provider.aclose()

    async def _steps(
        self, provider: Provider, model: str, run_id: str, messages: list[Message]
    ) -> str:
        specs = tool_specs()
        final: list[str] = []
        for _ in range(max_steps()):
            content = ""
            calls: list[ToolCall] = []
            async with aclosing(provider.stream(messages, specs, model=model)) as events:
                async for event in events:
                    if isinstance(event, TextDelta):
                        content += event.text
                        self.store.add_event(run_id, "message.delta", {"delta": event.text})
                    elif isinstance(event, ToolCall):
                        calls.append(event)
                    # Usage and Finish are not persisted in S0 (usage tracking is S2).
            if content:
                final.append(content)
            if not calls:
                if not content:
                    raise ValueError("模型没有返回可显示的内容")
                return "\n\n".join(final)
            messages.append(
                Message(role="assistant", content=content or None, tool_calls=tuple(calls))
            )
            for call in calls:
                result = await self._execute_call(run_id, call)
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps(result, ensure_ascii=False),
                    )
                )
        raise ValueError("已达到最大工具执行步数")

    async def _execute_call(self, run_id: str, call: ToolCall) -> Any:
        # Malformed JSON goes back to the model as a tool error instead of failing the run.
        try:
            arguments = json.loads(call.arguments)
        except ValueError:
            return INVALID_ARGUMENTS
        return await self.call_tool(run_id, call.name, arguments)
