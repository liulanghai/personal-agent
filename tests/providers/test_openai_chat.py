"""OpenAIChatProvider against recorded-shape SSE streams (httpx.MockTransport, no network)."""

import asyncio
import json
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import pytest

from agent.providers.base import (
    Finish,
    Message,
    ProviderError,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)
from agent.providers.openai_chat import OpenAIChatProvider, classify_status, to_chat_message

Handler = Callable[[httpx.Request], httpx.Response]
TOOLS = [ToolSpec(name="list_files", description="List files.", parameters={"type": "object"})]


def sse_body(*chunks: dict[str, Any] | str, done: bool = True) -> str:
    lines = [c if isinstance(c, str) else "data: " + json.dumps(c) for c in chunks]
    if done:
        lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


def delta(**fields: Any) -> dict[str, Any]:
    return {"choices": [{"index": 0, "delta": fields}]}


def fragment(index: int, **fields: Any) -> dict[str, Any]:
    return {"index": index, **fields}


def collect(
    handler: Handler, messages: Sequence[Message] = (Message(role="user", content="hi"),)
) -> list[StreamEvent]:
    async def run() -> list[StreamEvent]:
        provider = OpenAIChatProvider(
            base_url="https://model.example/v1/",
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )
        try:
            return [event async for event in provider.stream(messages, TOOLS, model="m")]
        finally:
            await provider.aclose()

    return asyncio.run(run())


def respond(body: str, status: int = 200) -> Handler:
    return lambda request: httpx.Response(status, content=body)


def test_text_only_stream() -> None:
    events = collect(
        respond(sse_body(delta(role="assistant"), delta(content="你好"), delta(content="！")))
    )
    assert events == [TextDelta("你好"), TextDelta("！"), Finish("stop")]


def test_tool_arguments_split_across_chunks_are_assembled() -> None:
    body = sse_body(
        delta(
            tool_calls=[
                fragment(
                    0, id="call_1", type="function", function={"name": "read_", "arguments": ""}
                )
            ]
        ),
        delta(tool_calls=[fragment(0, function={"name": "file", "arguments": '{"pa'})]),
        delta(tool_calls=[fragment(0, function={"arguments": 'th": "a.md"}'})]),
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    )
    assert collect(respond(body)) == [
        ToolCall(id="call_1", name="read_file", arguments='{"path": "a.md"}'),
        Finish("tool_calls"),
    ]


def test_interleaved_parallel_calls_are_emitted_in_index_order() -> None:
    body = sse_body(
        delta(
            tool_calls=[
                fragment(1, id="call_b", function={"name": "list_skills", "arguments": "{"})
            ]
        ),
        delta(
            tool_calls=[fragment(0, id="call_a", function={"name": "list_files", "arguments": "{"})]
        ),
        delta(
            tool_calls=[
                fragment(1, function={"arguments": "}"}),
                fragment(0, function={"arguments": "}"}),
            ]
        ),
    )
    assert collect(respond(body)) == [
        ToolCall(id="call_a", name="list_files", arguments="{}"),
        ToolCall(id="call_b", name="list_skills", arguments="{}"),
        Finish("tool_calls"),
    ]


def test_text_and_tool_call_in_same_turn() -> None:
    body = sse_body(
        delta(content="先看看文件"),
        delta(tool_calls=[fragment(0, id="c", function={"name": "list_files", "arguments": "{}"})]),
    )
    assert collect(respond(body)) == [
        TextDelta("先看看文件"),
        ToolCall(id="c", name="list_files", arguments="{}"),
        Finish("tool_calls"),
    ]


def test_usage_chunk_with_empty_choices_and_comments_are_handled() -> None:
    body = sse_body(
        ": keepalive comment",
        delta(content="ok"),
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
    )
    assert collect(respond(body)) == [
        TextDelta("ok"),
        Usage(input_tokens=12, output_tokens=3),
        Finish("stop"),
    ]


def test_missing_done_marker_still_finishes() -> None:
    assert collect(respond(sse_body(delta(content="end"), done=False))) == [
        TextDelta("end"),
        Finish("stop"),
    ]


def test_length_and_unknown_finish_reasons() -> None:
    body = sse_body(
        {"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "length"}]}
    )
    assert collect(respond(body))[-1] == Finish("length")
    body = sse_body(
        {"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "weird"}]}
    )
    assert collect(respond(body))[-1] == Finish("other")


def test_non_json_arguments_are_passed_through_unparsed() -> None:
    body = sse_body(
        delta(
            tool_calls=[
                fragment(0, id="c", function={"name": "read_file", "arguments": "{not json"})
            ]
        )
    )
    assert collect(respond(body))[0] == ToolCall(id="c", name="read_file", arguments="{not json")


def test_malformed_sse_payload_raises_provider_error() -> None:
    with pytest.raises(ProviderError) as error:
        collect(respond("data: {broken\n\n"))
    assert error.value.kind == "other" and not error.value.retryable


@pytest.mark.parametrize(
    ("status", "body", "kind", "retryable"),
    [
        (401, b"{}", "auth", False),
        (403, b"{}", "auth", False),
        (429, b"{}", "rate_limit", True),
        (500, b"{}", "server", True),
        (503, b"{}", "server", True),
        (400, b'{"error":{"code":"context_length_exceeded"}}', "context_length", False),
        (400, b"{}", "bad_request", False),
        (404, b"{}", "bad_request", False),
    ],
)
def test_http_errors_are_classified_without_leaking_body(
    status: int, body: bytes, kind: str, retryable: bool
) -> None:
    leaky = body[:-1] + b',"echo":"sk-test-leak"}'
    with pytest.raises(ProviderError) as error:
        collect(respond(leaky.decode(), status))
    assert (error.value.kind, error.value.retryable, error.value.status_code) == (
        kind,
        retryable,
        status,
    )
    assert str(error.value) == "模型服务返回 HTTP " + str(status) + "，请检查设置、模型权限或额度"
    assert "sk-test-leak" not in str(error.value)
    assert classify_status(status, body) == (kind, retryable)


def test_network_errors_are_retryable_provider_errors() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderError) as error:
        collect(fail)
    assert error.value.kind == "network" and error.value.retryable
    assert str(error.value) == "执行失败（ConnectError），请检查模型连接或本地文件"


def test_request_shape_and_message_mapping() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=sse_body(delta(content="ok")))

    call = ToolCall(id="c1", name="list_files", arguments="{}")
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(role="assistant", content=None, tool_calls=(call,)),
        Message(role="tool", tool_call_id="c1", content='["a.md"]'),
    ]
    collect(handler, messages)
    request = seen[0]
    assert str(request.url) == "https://model.example/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "m" and body["stream"] is True
    assert "stream_options" not in body
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files.",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "list_files", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '["a.md"]'},
    ]
    assert to_chat_message(Message(role="assistant", content="plain")) == {
        "role": "assistant",
        "content": "plain",
    }


def test_redirects_are_not_followed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(307, headers={"location": "https://evil.example/steal"})

    # Same as before the refactor: an empty non-error response yields no content,
    # and the loop reports "模型没有返回可显示的内容". The key is never re-sent.
    assert collect(handler) == [Finish("stop")]
    assert [str(r.url) for r in seen] == ["https://model.example/v1/chat/completions"]
