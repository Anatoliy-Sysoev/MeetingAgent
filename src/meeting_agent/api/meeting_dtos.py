from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicLastError(PublicModel):
    stage: str | None = None
    code: str
    timestamp: str | None = None
    detail: str


class MediaMetadata(PublicModel):
    media_id: str
    filename: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str | None = None
    duration_sec: float | None = Field(default=None, ge=0)
    view_url: str


class MeetingSummary(PublicModel):
    meeting_id: str
    title: str
    date: str | None = None
    language: str | None = None
    source_kind: str | None = None
    processing_status: str
    created_at: str | None = None
    updated_at: str | None = None
    artifacts_count: int = Field(ge=0)
    artifact_keys: list[str] = Field(default_factory=list)
    media_count: int = Field(ge=0)
    workspace_url: str
    artifacts_url: str
    media_url: str
    last_error: PublicLastError | None = None


class MeetingListError(PublicModel):
    meeting_id: str | None = None
    code: str
    detail: str


class MeetingListResponse(PublicModel):
    items: list[MeetingSummary]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    errors: list[MeetingListError] = Field(default_factory=list)


class MeetingSource(PublicModel):
    kind: str | None = None
    audio_tracks: list[str] = Field(default_factory=list)
    derived_tracks: list[str] = Field(default_factory=list)


class MeetingClassification(PublicModel):
    project_stage: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    needs_review: bool | None = None


class MeetingRetention(PublicModel):
    policy: str | None = None
    review_after: str | None = None
    media_delete_after_days: int | None = Field(default=None, ge=0)


class MeetingRagStatus(PublicModel):
    index_policy: str | None = None
    indexed: bool
    indexed_artifacts_count: int = Field(ge=0)
    last_indexed_at: str | None = None


class MeetingDetail(MeetingSummary):
    schema_version: int | None = None
    start_time: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    participants: list[str] = Field(default_factory=list)
    source: MeetingSource
    classification: MeetingClassification
    retention: MeetingRetention
    rag: MeetingRagStatus
    media: list[MediaMetadata] = Field(default_factory=list)


class ArtifactMetadata(PublicModel):
    artifact_id: str
    key: str
    exists: bool
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    modified_at: str | None = None
    view_url: str | None = None
    error: str | None = None


class ArtifactListResponse(PublicModel):
    meeting_id: str
    artifacts: list[ArtifactMetadata]


class MediaListResponse(PublicModel):
    meeting_id: str
    media: list[MediaMetadata]
