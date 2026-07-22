"""Tests for the meeting artifact manifest (MA-MEETING-ARTIFACT-CONTRACT, #119)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.jobs.runner import JobRunner  # noqa: E402
from asu_june_bot.meetings.manifest import build_artifact_manifest  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-manifest-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MEETING_ID = "2026-03-03__manifest"

CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "Manifest Meeting",
    "date": "2026-03-03",
    "processing_status": "new",
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
}

EXPECTED_KEYS = [
    "segments", "transcript_txt", "transcription_report",
    "live_refinement_mic", "live_refinement_sys", "live_diarization_sys",
    "diarization",
    "speaker_transcript", "chunks", "enriched_chunks", "memo", "protocol",
    "decisions", "tasks", "risks", "open_questions", "index_status",
    "structured_index_status",
]


def _make_meeting(root: Path, card_extra: dict | None = None) -> Path:
    d = root / MEETING_ID
    d.mkdir(parents=True, exist_ok=True)
    (d / "meeting.json").write_text(
        json.dumps({**CARD, **(card_extra or {})}), encoding="utf-8"
    )
    return d


def _touch(meeting_dir: Path, rel: str, content: str = "x") -> None:
    p = meeting_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _by_key(manifest: dict) -> dict[str, dict]:
    return {e["artifact_key"]: e for e in manifest["artifacts"]}


# ---------------------------------------------------------------------------
# Unit — build_artifact_manifest
# ---------------------------------------------------------------------------

def test_manifest_covers_all_stages(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    manifest = build_artifact_manifest(MEETING_ID, d, CARD)
    entries = _by_key(manifest)
    assert list(entries) == EXPECTED_KEYS
    stages = {e["stage"] for e in entries.values()}
    assert stages == {
        "transcribe", "diarize", "merge", "chunk", "enrich", "analyze",
        "index", "index_artifacts",
    }


def test_missing_artifacts_reported_absent(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, CARD))
    for key in EXPECTED_KEYS:
        assert entries[key]["exists"] is False
        assert entries[key]["size_bytes"] is None
        assert entries[key]["updated_at"] is None
        assert entries[key]["view_url"] is None


def test_existing_artifact_has_metadata_and_urls(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    rel = "transcript/segments.jsonl"
    _touch(d, rel, '{"a":1}\n')
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, CARD))
    seg = entries["segments"]
    assert seg["exists"] is True
    assert seg["size_bytes"] == (d / rel).stat().st_size
    assert seg["updated_at"] is not None
    assert seg["view_url"] == f"/meetings/{MEETING_ID}/artifacts/segments"
    assert seg["download_url"] == seg["view_url"]
    assert seg["content_type"] == "jsonl"
    assert seg["stage"] == "transcribe"


def test_card_artifact_path_overrides_default(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path, {"artifacts": {"memo": "artifacts/custom_summary.md"}})
    _touch(d, "artifacts/custom_summary.md", "# Summary")
    card = json.loads((d / "meeting.json").read_text(encoding="utf-8"))
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, card))
    assert entries["memo"]["exists"] is True


def test_traversal_artifact_path_reported_invalid(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path, {"artifacts": {"memo": "../../etc/passwd"}})
    card = json.loads((d / "meeting.json").read_text(encoding="utf-8"))
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, card))
    memo = entries["memo"]
    assert memo["exists"] is False
    assert memo["error"] == "invalid_artifact_path"
    assert "etc" not in json.dumps(memo)


def test_malformed_artifacts_map_tolerated(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path, {"artifacts": "not-a-dict"})
    card = json.loads((d / "meeting.json").read_text(encoding="utf-8"))
    manifest = build_artifact_manifest(MEETING_ID, d, card)
    assert len(manifest["artifacts"]) == len(EXPECTED_KEYS)


def test_directory_instead_of_file_is_absent(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    (d / "transcript" / "segments.jsonl").mkdir(parents=True)
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, CARD))
    assert entries["segments"]["exists"] is False


def test_index_status_from_rag(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path, {"rag": {"indexed_artifacts": ["artifacts/enriched_chunks.jsonl"]}})
    card = json.loads((d / "meeting.json").read_text(encoding="utf-8"))
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, card))
    idx = entries["index_status"]
    assert idx["exists"] is True
    assert idx["content_type"] == "status"
    assert idx["view_url"] is None


def test_structured_index_status_requires_every_structured_artifact(tmp_path: Path) -> None:
    indexed = [
        "artifacts/decisions.json",
        "artifacts/tasks.json",
        "artifacts/risks.json",
        "artifacts/open_questions.json",
    ]
    d = _make_meeting(tmp_path, {"rag": {"indexed_artifacts": indexed}})
    card = json.loads((d / "meeting.json").read_text(encoding="utf-8"))
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, card))

    assert entries["structured_index_status"]["exists"] is True
    assert entries["structured_index_status"]["stage"] == "index_artifacts"

    card["rag"]["indexed_artifacts"].pop()
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, card))
    assert entries["structured_index_status"]["exists"] is False


def test_no_absolute_paths_in_manifest(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "transcript/segments.jsonl")
    _touch(d, "artifacts/summary.md")
    manifest = build_artifact_manifest(MEETING_ID, d, CARD)
    dumped = json.dumps(manifest)
    assert str(tmp_path) not in dumped
    assert str(d) not in dumped


# ---------------------------------------------------------------------------
# API — GET /meetings/{id}/artifacts/manifest
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    local_auth_service: LocalAuthService
    admin_service: AdminService = field(default=None)  # type: ignore[assignment]
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _make_client(root: Path) -> TestClient:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(root / "_auth.db")
    repo.initialize()
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(root),
        job_runner=JobRunner(),
        local_auth_service=LocalAuthService(repo),
        admin_service=AdminService(repo),
    )
    return client


def test_api_manifest_route_not_captured_as_artifact_name(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "transcript/segments.jsonl")
    client = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/artifacts/manifest", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    assert [e["artifact_key"] for e in body["artifacts"]] == EXPECTED_KEYS


def test_api_unknown_meeting_404(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.get("/meetings/missing__x/artifacts/manifest", headers=AUTH)
    assert resp.status_code == 404


def test_api_unreadable_card_returns_default_manifest(tmp_path: Path) -> None:
    d = tmp_path / MEETING_ID
    d.mkdir(parents=True)
    (d / "meeting.json").write_text("{broken json", encoding="utf-8")
    client = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/artifacts/manifest", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()["artifacts"]) == len(EXPECTED_KEYS)


def test_transcription_report_in_catalog(tmp_path: Path) -> None:
    d = _make_meeting(tmp_path)
    _touch(d, "transcript/transcription_report.json", "{}")
    entries = _by_key(build_artifact_manifest(MEETING_ID, d, CARD))
    report = entries["transcription_report"]
    assert report["stage"] == "transcribe"
    assert report["content_type"] == "json"
    assert report["exists"] is True


def test_api_every_view_url_is_servable(tmp_path: Path) -> None:
    """Every non-null view_url in the manifest must be served by the viewer,
    including default-path artifacts not registered in meeting.json.artifacts."""
    d = _make_meeting(tmp_path)  # artifacts map intentionally empty
    _touch(d, "transcript/segments.jsonl", '{"a":1}\n')
    _touch(d, "transcript/transcript.txt", "text")
    _touch(d, "transcript/transcription_report.json", "{}")
    _touch(d, "transcript/live/refinement.MIC.json", "{}")
    _touch(d, "transcript/live/refinement.SYS.json", "{}")
    _touch(d, "transcript/live/live_diarization.SYS.json", "{}")
    _touch(d, "transcript/diarization.jsonl", '{"s":1}\n')
    _touch(d, "transcript/speaker_transcript.jsonl", '{"s":1}\n')
    _touch(d, "transcript/chunks.jsonl", '{"c":1}\n')
    _touch(d, "artifacts/enriched_chunks.jsonl", '{"c":1}\n')
    _touch(d, "artifacts/summary.md", "# S")
    _touch(d, "artifacts/protocol.md", "# P")
    _touch(d, "artifacts/decisions.json", "[]")
    _touch(d, "artifacts/tasks.json", "[]")
    _touch(d, "artifacts/risks.json", "[]")
    _touch(d, "artifacts/open_questions.json", "[]")
    client = _make_client(tmp_path)
    manifest = client.get(f"/meetings/{MEETING_ID}/artifacts/manifest", headers=AUTH).json()
    urls = [e["view_url"] for e in manifest["artifacts"] if e["view_url"]]
    assert len(urls) == len(EXPECTED_KEYS) - 2  # status entries have no files
    for url in urls:
        resp = client.get(url, headers=AUTH)
        assert resp.status_code == 200, f"{url} → {resp.status_code}"
        assert "error" not in resp.json(), f"{url} → {resp.json()}"


def test_api_requires_auth(tmp_path: Path) -> None:
    _make_meeting(tmp_path)
    client = _make_client(tmp_path)
    resp = client.get(f"/meetings/{MEETING_ID}/artifacts/manifest")
    assert resp.status_code == 401
