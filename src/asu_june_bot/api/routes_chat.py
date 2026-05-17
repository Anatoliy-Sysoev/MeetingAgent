from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from asu_june_bot.api.dependencies import get_chat_service
from asu_june_bot.chat import ChatRequest, ChatService
from asu_june_bot.core.limits import MAX_QUERY_CHARS


router = APIRouter(tags=["chat"])


class ChatApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS, description="Project chat query")
    mode: Literal["hybrid", "vector", "bm25"] = "hybrid"
    top_k: int = Field(default=8, ge=1, le=50)
    include_source_types: list[str] | None = None
    model: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=900, ge=1, le=4096)
    timeout_sec: int = Field(default=300, ge=1, le=1800)
    include_diagnostics: bool = True


@router.post("/chat")
def chat(
    payload: ChatApiRequest,
    request: Request,
    service: ChatService = Depends(get_chat_service),
) -> dict:
    result = service.chat(
        ChatRequest(
            query=payload.query,
            mode=payload.mode,
            top_k=payload.top_k,
            include_source_types=payload.include_source_types,
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            timeout_sec=payload.timeout_sec,
            include_diagnostics=payload.include_diagnostics,
        )
    ).to_dict()
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        result.setdefault("diagnostics", {})["request_id"] = request_id
    return result
