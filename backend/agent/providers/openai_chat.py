"""OpenAI Chat Completions adapter (also used by compatible endpoints).

Responsibilities that live here and nowhere else:
- neutral ``Message``/``ToolSpec`` -> Chat Completions request JSON
- SSE parsing (``data:`` lines, ``[DONE]``, chunks with empty ``choices``)
- assembling streamed tool-call fragments by ``index`` into complete ``ToolCall``s
- HTTP status / transport failures -> ``ProviderError``

Provider response bodies are never logged or put into error messages: they
may echo credentials. Error classification inspects a bounded prefix. Explicitly
opted-in learning records keep sanitized bodies in a dedicated local store.
"""

import asyncio
import json
import re
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import asdict
from typing import Any

import httpx

from ..config import Settings
from .base import (
    Finish,
    FinishReason,
    Message,
    ProviderError,
    ProviderErrorKind,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)
from .recording import Recorder, recording_scope

TIMEOUT_SECONDS = 90
ERROR_BODY_PEEK = 4096
FINISH_REASONS: dict[str, FinishReason] = {
    "stop": "stop",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "length": "length",
    "content_filter": "content_filter",
}


def to_chat_message(message: Message) -> dict[str, Any]:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ],
        }
    return {"role": message.role, "content": message.content}


def to_chat_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def classify_status(status_code: int, body: bytes) -> tuple[ProviderErrorKind, bool]:
    """Map an HTTP error status to (kind, retryable)."""
    if status_code in (401, 403):
        return "auth", False
    if status_code == 429:
        return "rate_limit", True
    if status_code == 408:
        return "network", True
    if status_code >= 500:
        return "server", True
    if status_code == 400 and b"context_length_exceeded" in body:
        return "context_length", False
    if 400 <= status_code < 500:
        return "bad_request", False
    return "other", False


class _ToolCallBuffer:
    """Accumulates streamed tool-call fragments keyed by their ``index``."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def add(self, fragment: dict[str, Any]) -> None:
        if not isinstance(fragment["index"], int):
            raise ValueError("Invalid tool call index")
        current = self._calls.setdefault(fragment["index"], {"id": "", "name": "", "arguments": ""})
        if fragment.get("id"):
            current["id"] = fragment["id"]
        function = fragment.get("function") or {}
        current["name"] += function.get("name") or ""
        current["arguments"] += function.get("arguments") or ""

    def __bool__(self) -> bool:
        return bool(self._calls)

    def complete(self) -> list[ToolCall]:
        return [
            ToolCall(id=call["id"], name=call["name"], arguments=call["arguments"])
            for _, call in sorted(self._calls.items())
        ]


class OpenAIChatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        # One client per provider instance (= per run), so steps reuse connections.
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=self._transport
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], *, model: str
    ) -> AsyncGenerator[StreamEvent, None]:
        body = {
            "model": model,
            "messages": [to_chat_message(m) for m in messages],
            "tools": [to_chat_tool(t) for t in tools],
            "stream": True,
        }
        scope = recording_scope.get()
        recorder = Recorder(scope, self.url, self.api_key, body) if scope else None
        status, error = "completed", None
        try:
            async with self._http().stream(
                "POST",
                self.url,
                headers={"Authorization": "Bearer " + self.api_key},
                json=body,
            ) as response:
                if recorder:
                    recorder.record["http_status"] = response.status_code
                    recorder.save()
                if response.status_code >= 400:
                    raise await self._status_error(response, recorder)
                async for event in self._parse(response, recorder):
                    yield event
        except (asyncio.CancelledError, GeneratorExit):
            status, error = "cancelled", "调用已取消"
            raise
        except httpx.TransportError as exc:
            status = "failed"
            error = "执行失败（" + type(exc).__name__ + "），请检查模型连接或本地文件"
            raise ProviderError("network", error, retryable=True) from exc
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            # Conversion errors may quote arbitrary response values, including credentials.
            status, error = "failed", "模型服务返回了无法解析的流数据"
            raise ProviderError("other", error, retryable=False) from None
        except Exception as exc:
            status = "failed"
            error = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
            raise
        finally:
            if recorder:
                recorder.finish(status, error)

    async def _status_error(
        self, response: httpx.Response, recorder: Recorder | None = None
    ) -> ProviderError:
        peek = b""
        async for text in response.aiter_text():
            if recorder:
                recorder.receive(text)
            peek = (peek + text.encode())[:ERROR_BODY_PEEK]
            if recorder is None and len(peek) >= ERROR_BODY_PEEK:
                break
        if recorder:
            try:
                recorder.record["response"]["body"] = json.loads(recorder.raw)
            except ValueError:
                pass  # Non-JSON error bodies remain available in the raw record.
        kind, retryable = classify_status(response.status_code, peek[:ERROR_BODY_PEEK])
        return ProviderError(
            kind,
            "模型服务返回 HTTP " + str(response.status_code) + "，请检查设置、模型权限或额度",
            retryable=retryable,
            status_code=response.status_code,
        )

    async def _lines(
        self, response: httpx.Response, recorder: Recorder | None
    ) -> AsyncIterator[str]:
        buffer = ""
        async for text in response.aiter_text():
            if recorder:
                recorder.receive(text)
            buffer += text
            lines = re.split(r"\r\n|\r|\n", buffer)
            buffer = lines.pop()
            for line in lines:
                yield line
        if buffer:
            yield buffer

    async def _parse(
        self, response: httpx.Response, recorder: Recorder | None = None
    ) -> AsyncGenerator[StreamEvent, None]:
        calls = _ToolCallBuffer()
        reason: FinishReason | None = None
        usage: Usage | None = None
        content = ""
        async for line in self._lines(response, recorder):
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                if not isinstance(chunk, dict) or "error" in chunk:
                    raise ValueError("Invalid stream payload")
            except ValueError:
                raise ProviderError(
                    "other", "模型服务返回了无法解析的流数据", retryable=False
                ) from None
            if chunk.get("usage"):
                usage = Usage(
                    input_tokens=int(chunk["usage"].get("prompt_tokens") or 0),
                    output_tokens=int(chunk["usage"].get("completion_tokens") or 0),
                )
            if recorder and chunk.get("usage"):
                recorder.record["response"]["usage"] = chunk["usage"]
                recorder.save()
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            content += delta.get("content") or ""
            for fragment in delta.get("tool_calls") or []:
                calls.add(fragment)
            if choice.get("finish_reason"):
                reason = FINISH_REASONS.get(choice["finish_reason"], "other")
            if recorder:
                recorder.record["response"].update(
                    content=content,
                    tool_calls=[asdict(call) for call in calls.complete()],
                    finish_reason=reason,
                )
                recorder.save()
            if delta.get("content"):
                yield TextDelta(delta["content"])
        # Many compatible endpoints omit finish_reason; infer it from the content.
        reason = reason or ("tool_calls" if calls else "stop")
        if recorder:
            recorder.record["response"]["finish_reason"] = reason
            recorder.save()
        for call in calls.complete():
            yield call
        if usage is not None:
            yield usage
        yield Finish(reason)


def from_settings(settings: Settings) -> OpenAIChatProvider:
    return OpenAIChatProvider(base_url=settings["base_url"], api_key=settings.get("api_key", ""))
