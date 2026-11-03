"""ScriptedProvider: a deterministic Provider test double.

Each call to ``stream`` consumes the next step of a script. A step is either a
fixed sequence of events or a function of the messages the model would see,
which lets a test react to tool results without parsing prompts. Every request
is recorded so tests can assert on what the runtime sent.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any

from agent.config import Settings
from agent.providers.base import Finish, Message, StreamEvent, TextDelta, ToolCall, ToolSpec

Step = Sequence[StreamEvent] | Callable[[Sequence[Message]], Sequence[StreamEvent]]


def call(name: str, arguments: dict[str, Any] | str | None = None, call_id: str = "") -> ToolCall:
    """A complete tool call; dict arguments are JSON-encoded, strings passed through raw."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments or {})
    return ToolCall(id=call_id or "call_" + name, name=name, arguments=raw)


def tool_turn(*calls: ToolCall) -> list[StreamEvent]:
    return [*calls, Finish("tool_calls")]


def text_turn(text: str) -> list[StreamEvent]:
    return [TextDelta(text), Finish("stop")]


class ScriptedProvider:
    def __init__(self, steps: Sequence[Step], *, delay: float = 0.0) -> None:
        self.steps = list(steps)
        self.delay = delay
        self.requests: list[list[Message]] = []
        self.tools: list[list[ToolSpec]] = []
        self.models: list[str] = []
        self.closed = False

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], *, model: str
    ) -> AsyncGenerator[StreamEvent, None]:
        index = len(self.requests)
        self.requests.append(list(messages))
        self.tools.append(list(tools))
        self.models.append(model)
        if self.delay:
            await asyncio.sleep(self.delay)
        if index >= len(self.steps):
            raise AssertionError("ScriptedProvider has no step " + str(index + 1))
        step = self.steps[index]
        for event in step(messages) if callable(step) else step:
            yield event

    async def aclose(self) -> None:
        self.closed = True


class ScriptedProviderFactory:
    """``provider_factory`` for create_app: a fresh ScriptedProvider per run."""

    def __init__(self, steps: Sequence[Step], *, delay: float = 0.0) -> None:
        self.steps = list(steps)
        self.delay = delay
        self.providers: list[ScriptedProvider] = []
        self.settings: list[Settings] = []

    def __call__(self, settings: Settings) -> ScriptedProvider:
        provider = ScriptedProvider(self.steps, delay=self.delay)
        self.providers.append(provider)
        self.settings.append(settings)
        return provider

    @property
    def last(self) -> ScriptedProvider:
        return self.providers[-1]
