"""Agent loop: call the model, stream text, execute tool calls, repeat.

PR2 keeps the direct Chat Completions + httpx implementation unchanged; PR3
replaces the HTTP details with a Provider abstraction.
"""

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any

import httpx

from ..config import Settings
from ..context.builder import ContextBuilder
from ..store import FileRow, RunRow, Store, uid
from ..tools.registry import DEFINITIONS, Tools

MAX_STEPS_DEFAULT = 16
MAX_STEPS_LIMIT = 32


def max_steps() -> int:
    return min(int(os.getenv("AGENT_MAX_STEPS", str(MAX_STEPS_DEFAULT))), MAX_STEPS_LIMIT)


class AgentLoop:
    def __init__(
        self,
        store: Store,
        tools: Tools,
        settings: Callable[[], Settings],
        context: ContextBuilder,
    ) -> None:
        self.store = store
        self.tools = tools
        self.settings = settings
        self.context = context

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
        config = self.settings()
        if not config.get("api_key") or not config.get("model"):
            raise ValueError("请先在设置中配置模型名称和 API 密钥")
        history = self.store.history(run["conversation_id"])
        messages, manifest = self.context.build(config, dict(run), files, history)
        self.store.add_event(run["id"], "context.built", manifest)
        final: list[str] = []
        async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
            for _ in range(max_steps()):
                content, ordered = await self._model_step(client, config, run["id"], messages)
                if content:
                    final.append(content)
                if not ordered:
                    if not content:
                        raise ValueError("模型没有返回可显示的内容")
                    return "\n\n".join(final)
                messages.append(
                    {"role": "assistant", "content": content or None, "tool_calls": ordered}
                )
                for call in ordered:
                    try:
                        arguments = json.loads(call["function"]["arguments"])
                        result = await self.call_tool(
                            run["id"], call["function"]["name"], arguments
                        )
                    except (ValueError, TypeError):
                        result = {"error": "Invalid tool arguments: expected JSON object"}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            raise ValueError("已达到最大工具执行步数")

    async def _model_step(
        self,
        client: httpx.AsyncClient,
        config: Settings,
        run_id: str,
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """One streamed Chat Completions request. Returns (text, ordered tool calls)."""
        calls: dict[int, dict[str, Any]] = {}
        content = ""
        async with client.stream(
            "POST",
            config["base_url"].rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + config.get("api_key", "")},
            json={
                "model": config["model"],
                "messages": messages,
                "tools": DEFINITIONS,
                "stream": True,
            },
        ) as response:
            if response.status_code >= 400:
                # Do not persist provider response bodies: they may contain credentials.
                raise ValueError(
                    "模型服务返回 HTTP "
                    + str(response.status_code)
                    + "，请检查设置、模型权限或额度"
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if delta.get("content"):
                    text = delta["content"]
                    content += text
                    self.store.add_event(run_id, "message.delta", {"delta": text})
                for tc in delta.get("tool_calls", []):
                    current = calls.setdefault(
                        tc["index"],
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if tc.get("id"):
                        current["id"] = tc["id"]
                    for key in ("name", "arguments"):
                        current["function"][key] += tc.get("function", {}).get(key, "")
        return content, [calls[k] for k in sorted(calls)]
