from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from asu_june_bot.api.dependencies import get_search_service
from asu_june_bot.core.limits import MAX_QUERY_CHARS
from asu_june_bot.search import SearchRequest, SearchService


router = APIRouter(tags=["search"])


class SearchApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS, description="Project search query")
    mode: Literal["hybrid", "vector", "bm25"] = "hybrid"
    top_k: int = Field(default=8, ge=1, le=50)
    include_source_types: list[str] | None = None
    no_guard: bool = False
    include_diagnostics: bool = True


@router.post("/search")
def search(
    payload: SearchApiRequest,
    request: Request,
    service: SearchService = Depends(get_search_service),
) -> dict:
    result = service.search(
        SearchRequest(
            query=payload.query,
            mode=payload.mode,
            top_k=payload.top_k,
            include_source_types=payload.include_source_types,
            no_guard=payload.no_guard,
            include_diagnostics=payload.include_diagnostics,
        )
    ).to_dict()
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        result.setdefault("diagnostics", {})["request_id"] = request_id
    return result
