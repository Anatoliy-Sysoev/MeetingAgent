"""Compatibility shim for shared MeetingAgent LLM contracts."""

from meeting_agent.shared.llm import LLMClient, LLMError, LLMRequest, LLMResponse

__all__ = ["LLMClient", "LLMRequest", "LLMResponse", "LLMError"]
