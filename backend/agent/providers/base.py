"""Provider-neutral message and stream types, and the Provider protocol.

The runtime only speaks these types. Each provider adapter translates them to
and from one vendor wire format, so the agent loop never sees HTTP, SSE or
vendor JSON. Inspired by openai-agents-python and pydantic-ai, but deliberately
minimal (see docs/features/s0-foundation.md ③ PR3).
"""

from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ..config import Settings

Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "tool_calls", "length", "content_filter", "other"]
ProviderErrorKind = Literal[
    "auth", "rate_limit", "context_length", "bad_request", "server", "network", "other"
]


@dataclass(frozen=True)
class ToolCall:
    """A complete tool call. ``arguments`` is the raw JSON text, never parsed here."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Finish:
    reason: FinishReason


StreamEvent = TextDelta | ToolCall | Usage | Finish


class ProviderError(Exception):
    """A classified model-service failure.

    ``str(error)`` is a user-facing message and must never contain provider
    response bodies (they may echo credentials). ``retryable`` is a hint only;
    S0 does not retry (retries belong to S1).
    """

    def __init__(
        self,
        kind: ProviderErrorKind,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind: ProviderErrorKind = kind
        self.retryable = retryable
        self.status_code = status_code


class Provider(Protocol):
    def stream(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], *, model: str
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream one model turn.

        Implemented as an async generator so callers can ``aclose()`` it on
        cancellation, which closes the underlying HTTP stream deterministically.

        Yields ``TextDelta`` as text arrives, then each complete ``ToolCall`` in
        the provider's call order, an optional ``Usage``, and finally ``Finish``.
        Raises ``ProviderError`` on failure.
        """
        ...

    async def aclose(self) -> None:
        """Release connections. Called once when the run's loop ends."""
        ...


ProviderFactory = Callable[[Settings], Provider]
