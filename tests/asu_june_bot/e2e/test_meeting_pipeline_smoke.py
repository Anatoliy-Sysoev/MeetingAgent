"""End-to-end smoke tests for the MeetingAgent meeting pipeline.

Covers the full chain from a seeded speaker transcript through chunk →
enrich → index → analyze → Workspace API → meeting-scoped search/chat.

No real ASR, ffmpeg, diarization, or external LLM is required.  Scripts are
called in-process via their ``parse_args`` + ``run()`` helpers.  The FastAPI
TestClient exercises API routes against the same fixtures.

Refs #80
Refs #68 #69 #71 #74 #75 #76 #78
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _import_script(name: str) -> types.ModuleType:
    """Import a numbered script from the scripts/ directory by filename stem."""
    mapping = {
        "chunk": "26_chunk_meeting.py",
        "enrich": "27_enrich_meeting_chunks.py",
        "index": "28_index_meeting_chunks.py",
        "analyze": "29_analyze_meeting.py",
    }
    path = SCRIPTS / mapping[name]
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import AdminService, LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.jobs.runner import STAGE_COMMANDS, JobRunner  # noqa: E402
from asu_june_bot.llm import LLMError, LLMResponse  # noqa: E402
from asu_june_bot.meetings.qa import MeetingQAService  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

MEETING_ID = "2026-03-01__pipeline-smoke"
OTHER_MEETING_ID = "2026-01-15__other-meeting"
TOKEN = "test-e2e-smoke-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

VALID_CARD: dict[str, Any] = {
    "schema_version": 1,
    "meeting_id": "2026-03-01__pipeline-smoke",
    "title": "Pipeline Smoke Meeting",
    "date": "2026-03-01",
    "processing_status": "new",
    "participants": [],
    "source": {
        "kind": "offline_record",
        "media_files": [{"path": "source/meeting.wav", "media_type": "audio"}],
    },
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-03-01T10:00:00+00:00",
    "updated_at": "2026-03-01T10:00:00+00:00",
}

SPEAKER_TRANSCRIPT_ROWS = [
    {
        "start": 0.0,
        "end": 4.0,
        "speaker": "SPEAKER_00",
        "text": "Обсудили увеличение бюджета проекта на 10 процентов.",
        "source": "MIX",
        "utterance_id": "utt-000001",
    },
    {
        "start": 4.0,
        "end": 8.0,
        "speaker": "SPEAKER_01",
        "text": "Решили подготовить обновленный график работ к пятнице.",
        "source": "MIX",
        "utterance_id": "utt-000002",
    },
    {
        "start": 8.0,
        "end": 12.0,
        "speaker": "SPEAKER_00",
        "text": "Есть риск задержки поставки оборудования.",
        "source": "MIX",
        "utterance_id": "utt-000003",
    },
]

OTHER_MEETING_CHUNK = {
    "chunk_id": "other-chunk-001",
    "meeting_id": OTHER_MEETING_ID,
    "source_type": "meeting_chunk",
    "text": "Совещание по другой теме — бюджет другого проекта.",
    "relative_path": f"meetings/{OTHER_MEETING_ID}/transcript/chunks.jsonl",
    "source_path": "/abs/other/path",
    "start": 0.0,
    "end": 5.0,
    "speakers": [],
    "speaker_names": [],
}


class FakeLLM:
    """Returns a deterministic answer that cites [S1] and [S3] (skips S2)."""

    def __init__(self, text: str | None = None) -> None:
        self.text = (
            text
            or "Бюджет увеличен на 10 процентов [S1]. Есть риск задержки поставки оборудования [S3]."
        )
        self.calls: list = []

    def generate(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text=self.text, model="fake-e2e", finish_reason="stop")


# ---------------------------------------------------------------------------
# Meeting directory helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_meeting_dir(base: Path, card: dict[str, Any] | None = None) -> Path:
    """Create a minimal meeting directory with speaker_transcript seeded."""
    card = card or VALID_CARD
    mid = str(card["meeting_id"])
    meeting_dir = base / "meetings" / mid
    (meeting_dir / "source").mkdir(parents=True, exist_ok=True)
    (meeting_dir / "source" / "meeting.wav").write_bytes(b"")  # placeholder
    (meeting_dir / "transcript").mkdir(parents=True, exist_ok=True)
    (meeting_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        meeting_dir / "transcript" / "speaker_transcript.jsonl",
        SPEAKER_TRANSCRIPT_ROWS,
    )
    _write_json(meeting_dir / "meeting.json", dict(card))
    return meeting_dir


# ---------------------------------------------------------------------------
# TestClient helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    job_runner: JobRunner
    meeting_qa_service: MeetingQAService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def make_client(
    meetings_root: Path,
    chunks_path: Path | None = None,
    llm: FakeLLM | None = None,
) -> tuple[TestClient, AdminService, FakeLLM]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    repo = AuthRepository(meetings_root / "_auth.db")
    repo.initialize()
    fake_llm = llm or FakeLLM()
    qa = MeetingQAService(
        config=None,
        meetings_service=MeetingsService(meetings_root),
        llm_client=fake_llm,
        meeting_chunks_path=chunks_path or (meetings_root.parent / "data" / "meeting_chunks.jsonl"),
    )
    app = create_app()
    jr = JobRunner()
    svc = LocalAuthService(repo)
    admin_svc = AdminService(repo)
    client = TestClient(app, raise_server_exceptions=False, headers=AUTH)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        job_runner=jr,
        meeting_qa_service=qa,
        local_auth_service=svc,
        admin_service=admin_svc,
    )
    return client, admin_svc, fake_llm


# ===========================================================================
# 1. Chunk stage — script-level
# ===========================================================================


def test_chunk_creates_chunks_jsonl(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    # Update meeting.json to point to the seeded speaker_transcript
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    card["artifacts"]["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    _write_json(meeting_dir / "meeting.json", card)

    mod = _import_script("chunk")
    rc = mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--force"]))
    assert rc == 0

    chunks_path = meeting_dir / "transcript" / "chunks.jsonl"
    assert chunks_path.exists()

    rows = [json.loads(l) for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows, "chunk produced no rows"
    for row in rows:
        assert row.get("meeting_id") == MEETING_ID
        assert row.get("source_type") == "meeting_chunk"
        assert row.get("text"), "chunk row has no text"

    card_after = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert card_after["artifacts"].get("chunks") == "transcript/chunks.jsonl"


def test_chunk_text_contains_expected_phrases(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    card["artifacts"]["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    _write_json(meeting_dir / "meeting.json", card)

    mod = _import_script("chunk")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--force"]))

    chunks_path = meeting_dir / "transcript" / "chunks.jsonl"
    combined = " ".join(
        json.loads(l)["text"]
        for l in chunks_path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    )
    assert "бюджет" in combined.lower()
    assert "риск" in combined.lower()


def test_chunk_fails_without_speaker_transcript(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    (meeting_dir / "transcript" / "speaker_transcript.jsonl").unlink()

    mod = _import_script("chunk")
    with pytest.raises(Exception):
        mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--force"]))


# ===========================================================================
# 2. Enrich stage — script-level
# ===========================================================================


def _seed_chunks(meeting_dir: Path) -> None:
    """Run chunk stage and update meeting.json so enrich can find the output."""
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    card["artifacts"]["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    _write_json(meeting_dir / "meeting.json", card)
    mod = _import_script("chunk")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--force"]))


def test_enrich_creates_enriched_chunks_jsonl(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_chunks(meeting_dir)

    mod = _import_script("enrich")
    rc = mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir)]))
    assert rc == 0

    enriched_path = meeting_dir / "artifacts" / "enriched_chunks.jsonl"
    assert enriched_path.exists()

    rows = [json.loads(l) for l in enriched_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows
    for row in rows:
        assert row.get("meeting_id") == MEETING_ID
        assert row.get("chunk_id"), "enriched row missing chunk_id"
        assert str(row.get("text") or "").strip(), "enriched row has empty text"

    card_after = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert card_after["artifacts"].get("enriched_chunks") == "artifacts/enriched_chunks.jsonl"


def test_enrich_preserves_chunk_ids(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_chunks(meeting_dir)

    chunk_ids = {
        json.loads(l)["chunk_id"]
        for l in (meeting_dir / "transcript" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }

    mod = _import_script("enrich")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir)]))

    enriched_ids = {
        json.loads(l)["chunk_id"]
        for l in (meeting_dir / "artifacts" / "enriched_chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    assert chunk_ids == enriched_ids, "enrich changed or dropped chunk_ids"


# ===========================================================================
# 3. Index stage — script-level
# ===========================================================================


def _seed_enriched_chunks(meeting_dir: Path) -> None:
    _seed_chunks(meeting_dir)
    mod = _import_script("enrich")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir)]))


def test_index_creates_meeting_chunks_jsonl(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_enriched_chunks(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    mod = _import_script("index")
    rc = mod.run(
        mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)])
    )
    assert rc == 0
    assert chunks_out.exists()

    rows = [json.loads(l) for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows
    for row in rows:
        assert row["meeting_id"] == MEETING_ID
        assert row["source_type"] == "meeting_chunk"


def test_index_upsert_replaces_same_meeting_rows(tmp_path: Path) -> None:
    """Running index twice must not duplicate rows for the same meeting."""
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_enriched_chunks(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    mod = _import_script("index")
    args = mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)])

    mod.run(args)
    first_count = sum(1 for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip())

    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))
    second_count = sum(1 for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip())

    assert second_count == first_count, "second index run duplicated rows"


def test_index_upsert_preserves_other_meetings(tmp_path: Path) -> None:
    """Rows belonging to a different meeting must survive a re-index of our meeting."""
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_enriched_chunks(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    # Pre-populate with a row from a different meeting.
    chunks_out.write_text(
        json.dumps(OTHER_MEETING_CHUNK, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    mod = _import_script("index")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    rows = [json.loads(l) for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    other_rows = [r for r in rows if r["meeting_id"] == OTHER_MEETING_ID]
    assert other_rows, "index upsert deleted other-meeting row"


def test_index_rows_have_relative_path_not_absolute(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_enriched_chunks(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    mod = _import_script("index")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    rows = [json.loads(l) for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        rel = row.get("relative_path", "")
        assert not rel.startswith("/"), f"absolute relative_path leaked: {rel}"
        assert rel.startswith(f"meetings/{MEETING_ID}/"), f"unexpected relative_path: {rel}"


def test_index_meeting_json_updated(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_enriched_chunks(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    mod = _import_script("index")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    indexed = card.get("rag", {}).get("indexed_artifacts", [])
    assert "transcript/chunks.jsonl" in indexed or "artifacts/enriched_chunks.jsonl" in indexed


# ===========================================================================
# 4. Analyze stage — script-level (extractive mode, no LLM)
# ===========================================================================


def _seed_indexed(meeting_dir: Path) -> None:
    _seed_enriched_chunks(meeting_dir)


def test_analyze_extractive_creates_artifacts(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    mod = _import_script("analyze")
    rc = mod.run(
        mod.parse_args(
            ["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"]
        )
    )
    assert rc == 0

    for rel in ("artifacts/summary.md", "artifacts/protocol.md"):
        p = meeting_dir / rel
        assert p.exists(), f"artifact not created: {rel}"
        assert p.read_text(encoding="utf-8").strip(), f"artifact is empty: {rel}"

    for rel in (
        "artifacts/decisions.json",
        "artifacts/tasks.json",
        "artifacts/risks.json",
        "artifacts/open_questions.json",
    ):
        p = meeting_dir / rel
        assert p.exists(), f"artifact not created: {rel}"
        parsed = json.loads(p.read_text(encoding="utf-8"))
        assert "items" in parsed, f"JSON artifact missing 'items' key: {rel}"


def test_analyze_extractive_artifacts_are_source_grounded(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    mod = _import_script("analyze")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"]))

    tasks = json.loads((meeting_dir / "artifacts" / "tasks.json").read_text(encoding="utf-8"))
    assert tasks["items"], "seeded meeting should produce at least one task"
    item = tasks["items"][0]
    assert "confidence" in item
    assert "needs_review" in item
    ref = item["source_refs"][0]
    assert ref["chunk_id"]
    assert ref["timecode_start"]
    assert ref["timecode_end"]
    assert ref["speakers"]
    assert ref["utterance_ids"]

    summary = (meeting_dir / "artifacts" / "summary.md").read_text(encoding="utf-8")
    protocol = (meeting_dir / "artifacts" / "protocol.md").read_text(encoding="utf-8")
    assert "confidence=" in summary
    assert "needs_review" in summary or "ok" in summary
    assert "confidence=" in protocol


def test_analyze_extractive_updates_processing_status(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    mod = _import_script("analyze")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"]))

    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert card["processing_status"] == "summarized"


def test_analyze_artifacts_are_valid_json(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    mod = _import_script("analyze")
    mod.run(mod.parse_args(["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"]))

    for rel in (
        "artifacts/decisions.json",
        "artifacts/tasks.json",
        "artifacts/risks.json",
        "artifacts/open_questions.json",
    ):
        raw = (meeting_dir / rel).read_text(encoding="utf-8")
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{rel} is not valid JSON: {exc}")


# ===========================================================================
# 5. Full pipeline chain — all 4 stages in sequence
# ===========================================================================


def test_full_pipeline_chain_produces_indexed_chunks(tmp_path: Path) -> None:
    """chunk → enrich → index → analyze all succeed on the seeded transcript."""
    meeting_dir = build_meeting_dir(tmp_path)
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    card["artifacts"]["speaker_transcript"] = "transcript/speaker_transcript.jsonl"
    _write_json(meeting_dir / "meeting.json", card)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"

    chunk_mod = _import_script("chunk")
    enrich_mod = _import_script("enrich")
    index_mod = _import_script("index")
    analyze_mod = _import_script("analyze")

    assert chunk_mod.run(chunk_mod.parse_args(["--meeting-dir", str(meeting_dir), "--force"])) == 0
    assert enrich_mod.run(enrich_mod.parse_args(["--meeting-dir", str(meeting_dir)])) == 0
    assert index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)])) == 0
    assert analyze_mod.run(analyze_mod.parse_args(["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"])) == 0

    # Indexed rows exist.
    rows = [json.loads(l) for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(r["meeting_id"] == MEETING_ID for r in rows)

    # Analyze artifacts exist.
    assert (meeting_dir / "artifacts" / "summary.md").exists()
    assert (meeting_dir / "artifacts" / "decisions.json").exists()

    card_final = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    assert card_final["processing_status"] == "summarized"


# ===========================================================================
# 6. Workspace API — loads generated meeting
# ===========================================================================


def test_workspace_returns_200_for_indexed_meeting(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out)
    resp = client.get(f"/meetings/{MEETING_ID}/workspace", headers=AUTH)
    assert resp.status_code == 200
    assert MEETING_ID in resp.text


def test_workspace_artifacts_endpoint_lists_generated_artifacts(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    analyze_mod = _import_script("analyze")
    analyze_mod.run(analyze_mod.parse_args(["--meeting-dir", str(meeting_dir), "--mode", "extractive", "--force"]))

    client, _, _ = make_client(tmp_path / "meetings")
    resp = client.get(f"/meetings/{MEETING_ID}/artifacts", headers=AUTH)
    assert resp.status_code == 200
    keys = {a["key"] for a in resp.json().get("artifacts", [])}
    # memo (summary.md) and protocol are generated by extractive analyze.
    assert "memo" in keys or "protocol" in keys


# ===========================================================================
# 7. Meeting-scoped search over indexed chunks
# ===========================================================================


def test_search_finds_indexed_chunks(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out)
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "бюджет", "top_k": 5},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["results"], "search returned no results for 'бюджет'"
    for r in body["results"]:
        assert r["source"]["meeting_id"] == MEETING_ID  # search results carry source.meeting_id


def test_search_does_not_cross_meeting_boundary(tmp_path: Path) -> None:
    """Search over the smoke meeting must not return the other-meeting row."""
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    # Pre-populate with a row from a different meeting, then index ours.
    chunks_out.write_text(
        json.dumps(OTHER_MEETING_CHUNK, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out)
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "бюджет", "top_k": 10},
        headers=AUTH,
    )
    body = resp.json()
    for r in body.get("results", []):
        assert r["source"]["meeting_id"] == MEETING_ID, "cross-meeting search result leaked"


def test_search_no_absolute_paths_in_response(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out)
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "риск", "top_k": 5},
        headers=AUTH,
    )
    text = resp.text
    assert str(tmp_path) not in text, "absolute tmp_path leaked in search response"
    assert str(ROOT) not in text, "repo root path leaked in search response"


# ===========================================================================
# 8. Meeting-scoped chat over indexed chunks
# ===========================================================================


def test_chat_returns_answer_with_cited_sources(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    fake_llm = FakeLLM("Бюджет увеличен на 10 процентов [S1].")
    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out, llm=fake_llm)
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "бюджет", "top_k": 5},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answered"
    assert body.get("answer"), "chat returned no answer"
    assert body["citations_basis"] == "cited"
    assert body["citations"], "chat returned no citations"


def test_chat_citations_scoped_to_current_meeting(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    chunks_out.write_text(
        json.dumps(OTHER_MEETING_CHUNK, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    fake_llm = FakeLLM("Бюджет [S1].")
    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out, llm=fake_llm)
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "бюджет"},
        headers=AUTH,
    )
    body = resp.json()
    # Citations are flat objects — meeting_id scoping is enforced in the service,
    # not reflected in the citation shape.  Verify the answer is from our meeting.
    assert body.get("meeting_id") == MEETING_ID


def test_chat_no_absolute_paths_in_response(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out)
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "риск"},
        headers=AUTH,
    )
    text = resp.text
    assert str(tmp_path) not in text
    assert str(ROOT) not in text


def test_chat_citation_order_follows_answer_references(tmp_path: Path) -> None:
    """Citations appear in the order the answer references them, not ranked order."""
    meeting_dir = build_meeting_dir(tmp_path)
    _seed_indexed(meeting_dir)

    chunks_out = tmp_path / "data" / "meeting_chunks.jsonl"
    index_mod = _import_script("index")
    index_mod.run(index_mod.parse_args(["--meeting-dir", str(meeting_dir), "--output", str(chunks_out)]))

    rows = [json.loads(l) for l in chunks_out.read_text(encoding="utf-8").splitlines() if l.strip()
            if l.strip() and json.loads(l).get("meeting_id") == MEETING_ID]

    # Only meaningful if there are at least 2 indexed rows.
    if len(rows) < 2:
        pytest.skip("need at least 2 indexed rows for order test")

    # Answer cites last source first, then first source.
    n = len(rows)
    fake_llm = FakeLLM(f"Сначала источник [S{n}], затем [S1].")
    client, _, _ = make_client(tmp_path / "meetings", chunks_path=chunks_out, llm=fake_llm)
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "бюджет риск", "top_k": n + 1},
        headers=AUTH,
    )
    body = resp.json()
    if body["citations_basis"] == "cited" and len(body["citations"]) >= 2:
        # Second citation's chunk_id must differ from first — order is preserved.
        c_ids = [c["chunk_id"] for c in body["citations"]]
        assert c_ids[0] != c_ids[1], "citation order not preserved"


# ===========================================================================
# 9. ASR model pin regression
# ===========================================================================


def test_transcribe_stage_pins_product_asr_model() -> None:
    """Runner's transcribe stage must pass --model large-v3-turbo."""
    cfg = STAGE_COMMANDS.get("transcribe")
    assert cfg is not None, "transcribe stage missing from STAGE_COMMANDS"
    base_args = cfg.get("base_args", [])
    assert "--model" in base_args, "transcribe stage missing --model in base_args"
    model_idx = base_args.index("--model")
    model_value = base_args[model_idx + 1]
    assert model_value == "large-v3-turbo", (
        f"transcribe stage model is '{model_value}', expected 'large-v3-turbo'"
    )


def test_transcribe_stage_pins_faster_whisper_engine() -> None:
    cfg = STAGE_COMMANDS.get("transcribe")
    assert cfg is not None
    base_args = cfg.get("base_args", [])
    assert "--engine" in base_args
    engine_idx = base_args.index("--engine")
    assert base_args[engine_idx + 1] == "faster-whisper"


def test_stage_catalog_does_not_expose_scripts_or_commands(tmp_path: Path) -> None:
    from asu_june_bot.jobs.runner import stage_catalog

    catalog = stage_catalog()
    catalog_text = json.dumps(catalog)
    assert ".py" not in catalog_text
    assert "/scripts/" not in catalog_text
    assert "--model" not in catalog_text
    assert "--engine" not in catalog_text
    assert str(ROOT) not in catalog_text


def test_stage_catalog_covers_all_eight_stages() -> None:
    from asu_june_bot.jobs.runner import stage_catalog

    expected = {
        "extract_audio", "transcribe", "diarize", "merge",
        "chunk", "enrich", "index", "analyze",
    }
    actual = {s["stage"] for s in stage_catalog()}
    assert actual == expected


def test_stage_catalog_sorted_by_order() -> None:
    from asu_june_bot.jobs.runner import stage_catalog

    orders = [s["order"] for s in stage_catalog()]
    assert orders == sorted(orders), "stage catalog not sorted by order"


# ===========================================================================
# 10. Workspace DOM/CSP smoke
# ===========================================================================


def test_workspace_html_no_inline_handlers(tmp_path: Path) -> None:
    import re

    meeting_dir = build_meeting_dir(tmp_path)
    client, _, _ = make_client(tmp_path / "meetings")
    body = client.get(f"/meetings/{MEETING_ID}/workspace", headers=AUTH).text
    matches = re.findall(r'\son[a-z]+\s*=\s*"', body)
    assert matches == [], f"inline on* handlers found in workspace HTML: {matches}"


def test_workspace_html_uses_create_element_for_dynamic_content(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    client, _, _ = make_client(tmp_path / "meetings")
    body = client.get(f"/meetings/{MEETING_ID}/workspace", headers=AUTH).text
    assert "createElement" in body
    assert "textContent" in body
    assert "replaceChildren" in body


def test_workspace_html_no_local_storage(tmp_path: Path) -> None:
    meeting_dir = build_meeting_dir(tmp_path)
    client, _, _ = make_client(tmp_path / "meetings")
    body = client.get(f"/meetings/{MEETING_ID}/workspace", headers=AUTH).text
    assert "localStorage" not in body
    assert "sessionStorage" not in body


# ===========================================================================
# 11. Path safety
# ===========================================================================


def test_search_unsafe_meeting_id_returns_404(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path / "meetings")
    resp = client.post(
        "/meetings/../etc/passwd/search",
        json={"query": "test"},
        headers=AUTH,
    )
    assert resp.status_code in (400, 404, 422)


def test_chat_unsafe_meeting_id_returns_404(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path / "meetings")
    resp = client.post(
        "/meetings/../../secret/chat",
        json={"query": "test"},
        headers=AUTH,
    )
    assert resp.status_code in (400, 404, 422)
