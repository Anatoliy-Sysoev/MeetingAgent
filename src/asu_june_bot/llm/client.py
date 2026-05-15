from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMRequest:
    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 900
    timeout_sec: int = 300


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str | None = None
    finish_reason: str | None = None
    raw: dict = field(default_factory=dict)


class LLMClient(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
