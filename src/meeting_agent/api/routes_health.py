from __future__ import annotations

from fastapi import APIRouter

from meeting_agent import __version__


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Return a dependency-free liveness response safe for public probes."""
    return {
        "status": "ok",
        "service": "meetingagent",
        "version": __version__,
    }
