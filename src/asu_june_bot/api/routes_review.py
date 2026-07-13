from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from meeting_agent.api.auth import require_admin_action_permission, require_admin_user_permission
from meeting_agent.auth.models import Principal
from asu_june_bot.observability.review_queue import VALID_LABELS, ReviewQueue

router = APIRouter(prefix="/admin/review", tags=["review"])

_require_review_read = require_admin_user_permission("review.manage")
_require_review_write = require_admin_action_permission("review.manage")

_RUN_ID_MAX = 128


def _get_review_queue(request: Request) -> ReviewQueue:
    return request.app.state.asu_june_bot.review_queue


class LabelRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)
    manual_issue: str | None = Field(None, max_length=1000)
    comment: str | None = Field(None, max_length=2000)


@router.get("/chat-runs/export")
def export_chat_runs(
    request: Request,
    _principal: Annotated[Principal, Depends(_require_review_read)],
) -> dict:
    """Return all runs joined with their latest label (oldest first)."""
    queue = _get_review_queue(request)
    rows = queue.export_joined()
    return {"items": rows, "total": len(rows)}


@router.get("/chat-runs")
def list_chat_runs(
    request: Request,
    _principal: Annotated[Principal, Depends(_require_review_read)],
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = Query(default=None),
    guard_decision: str | None = Query(default=None),
    label: str | None = Query(default=None),
) -> dict:
    """Return up to limit recent chat runs with current label injected, newest first."""
    queue = _get_review_queue(request)
    runs = queue.list_runs(
        limit=limit,
        status=status,
        guard_decision=guard_decision,
        label=label,
    )
    return {"items": runs, "total": len(runs)}


@router.post("/chat-runs/{run_id}/label", status_code=200)
def set_run_label(
    run_id: str,
    payload: LabelRequest,
    request: Request,
    principal: Annotated[Principal, Depends(_require_review_write)],
) -> dict:
    """Append a label to the sidecar file for the given run_id."""
    if len(run_id) > _RUN_ID_MAX:
        raise HTTPException(status_code=422, detail="run_id too long")
    if payload.label not in VALID_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid label {payload.label!r}. Valid: {sorted(VALID_LABELS)}",
        )
    queue = _get_review_queue(request)
    record = queue.set_label(
        run_id=run_id,
        label=payload.label,
        manual_issue=payload.manual_issue,
        comment=payload.comment,
        labeled_by=principal.principal_id,
    )
    return record
