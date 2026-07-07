"""Shared LLM client contracts and adapters."""

from .client import LLMClient, LLMError, LLMRequest, LLMResponse

__all__ = ["LLMClient", "LLMRequest", "LLMResponse", "LLMError"]
