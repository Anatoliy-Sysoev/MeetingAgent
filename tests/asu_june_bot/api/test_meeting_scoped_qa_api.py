"""Tests for meeting-scoped search and chat: POST /meetings/{id}/search and /chat."""
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
from asu_june_bot.api.ui_assets import load_ui_asset  # noqa: E402
from asu_june_bot.auth.passwords import hash_password  # noqa: E402
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.llm import LLMError, LLMResponse  # noqa: E402
from asu_june_bot.meetings.qa import MeetingQAService  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "test-qa-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PASSWORD = "correct horse battery staple"

MEETING_ID = "2026-01-15__qa-test"
OTHER_MEETING_ID = "2026-02-02__other"

VALID_CARD = {
    "schema_version": 1,
    "meeting_id": MEETING_ID,
    "title": "QA Test Meeting",
    "date": "2026-01-15",
    "processing_status": "indexed",
    "participants": [],
    "source": {"kind": "offline_record"},
    "artifacts": {},
    "classification": {},
    "links": {},
    "retention": {"policy": "default"},
    "rag": {"index_policy": "structured_artifacts_and_final_transcript"},
    "created_at": "2026-01-15T10:00:00",
    "updated_at": "2026-01-15T11:00:00",
}

# Two in-scope chunks, one other-meeting chunk, one wrong source_type chunk.
CHUNK_ROWS = [
    {
        "chunk_id": "c1",
        "meeting_id": MEETING_ID,
        "source_type": "meeting_chunk",
        "text": "Обсудили бюджет проекта и сроки поставки.",
        "relative_path": f"meetings/{MEETING_ID}/transcript/chunks.jsonl",
        "source_path": "/abs/local/path/meetings/x/transcript/chunks.jsonl",
        "start": 0.0,
        "end": 12.0,
        "timestamp_start": "00:00:00",
        "timestamp_end": "00:00:12",
        "speakers": ["Иван"],
        "speaker_names": ["Иван"],
        "topic": "Бюджет",
    },
    {
        "chunk_id": "c2",
        "meeting_id": MEETING_ID,
        "source_type": "meeting_decision",
        "text": "Решение: увеличить бюджет на 10 процентов.",
        "relative_path": f"meetings/{MEETING_ID}/transcript/chunks.jsonl",
        "source_path": "/abs/local/path/meetings/x/transcript/chunks.jsonl",
        "start": 12.0,
        "end": 20.0,
        "timestamp_start": "00:00:12",
        "timestamp_end": "00:00:20",
        "speakers": ["Мария"],
        "speaker_names": ["Мария"],
        "topic": "Бюджет",
    },
    {
        "chunk_id": "other1",
        "meeting_id": OTHER_MEETING_ID,
        "source_type": "meeting_chunk",
        "text": "Бюджет совершенно другой встречи.",
        "relative_path": f"meetings/{OTHER_MEETING_ID}/transcript/chunks.jsonl",
        "start": 0.0,
        "end": 5.0,
        "speakers": [],
        "speaker_names": [],
    },
    {
        "chunk_id": "global1",
        "meeting_id": MEETING_ID,
        "source_type": "project_doc",  # not a meeting source type → must be filtered out
        "text": "Глобальный проектный документ про бюджет.",
        "relative_path": "docs/global.md",
        "start": 0.0,
        "end": 1.0,
    },
]


class FakeLLM:
    def __init__(self, text: str = "Бюджет увеличен на 10% [S1].") -> None:
        self.text = text
        self.calls: list = []

    def generate(self, request) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text=self.text, model="fake", finish_reason="stop")


class FailingLLM:
    def generate(self, request) -> LLMResponse:
        raise LLMError("provider down")


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    meeting_qa_service: MeetingQAService
    local_auth_service: LocalAuthService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _write_chunks(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def make_client(
    tmp_path: Path,
    *,
    chunks_rows: list[dict] | None = CHUNK_ROWS,
    chunks_exist: bool = True,
    llm=None,
) -> tuple[TestClient, AuthRepository, FakeLLM]:
    os.environ["MEETINGAGENT_API_TOKEN"] = TOKEN
    meetings_root = tmp_path / "meetings"
    (meetings_root / MEETING_ID).mkdir(parents=True)
    (meetings_root / MEETING_ID / "meeting.json").write_text(
        json.dumps(VALID_CARD), encoding="utf-8"
    )
    chunks_path = tmp_path / "data" / "meeting_chunks.jsonl"
    if chunks_exist:
        _write_chunks(chunks_path, chunks_rows or [])
    repo = AuthRepository(tmp_path / "auth.db")
    repo.initialize()
    fake_llm = llm or FakeLLM()
    qa = MeetingQAService(
        config=None,
        meetings_service=MeetingsService(meetings_root),
        llm_client=fake_llm,
        meeting_chunks_path=chunks_path,
    )
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False, headers=AUTH)
    app.state.asu_june_bot = FakeState(
        meetings_service=MeetingsService(meetings_root),
        meeting_qa_service=qa,
        local_auth_service=LocalAuthService(repo),
    )
    return client, repo, fake_llm


def _make_user(repo: AuthRepository, email: str, roles: set[str] | None = None) -> None:
    user = repo.create_user(email=email)
    repo.create_local_credential(user.user_id, hash_password(PASSWORD))
    # No roles → no permissions → 403 on permission-guarded routes.
    repo.set_user_roles(user.user_id, roles or set())


def _login(client: TestClient, email: str) -> tuple[str, str]:
    resp = client.post(
        "/auth/local/login",
        json={"email": email, "password": PASSWORD},
        headers={"Authorization": ""},
    )
    assert resp.status_code == 200, resp.json()
    return resp.cookies["ma_session"], resp.json()["csrf_token"]


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

def test_search_unauthenticated_401(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "бюджет"},
        headers={"Authorization": ""},
    )
    assert resp.status_code == 401


def test_search_missing_permission_403(tmp_path: Path) -> None:
    client, repo, _llm = make_client(tmp_path)
    _make_user(repo, "norights@example.com")  # unknown role → no permissions
    cookie, _csrf = _login(client, "norights@example.com")
    resp = client.post(
        f"/meetings/{MEETING_ID}/search",
        json={"query": "бюджет"},
        headers={"Authorization": ""},
        cookies={"ma_session": cookie},
    )
    assert resp.status_code == 403


def test_search_unknown_meeting_404(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post("/meetings/2099-09-09__ghost/search", json={"query": "бюджет"})
    assert resp.status_code == 404


def test_search_unsafe_meeting_id_returns_none() -> None:
    qa = MeetingQAService(meetings_service=MeetingsService(Path("/tmp/none")))
    assert qa.search("../etc/passwd", "бюджет") is None
    assert qa.search("bad/id", "бюджет") is None


def test_search_scoped_to_meeting_no_leakage(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/search", json={"query": "бюджет", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["meeting_id"] == MEETING_ID
    chunk_ids = {r["chunk_id"] for r in body["results"]}
    assert chunk_ids  # found something
    assert chunk_ids <= {"c1", "c2"}  # no other-meeting / global leakage
    assert "other1" not in chunk_ids
    assert "global1" not in chunk_ids
    for r in body["results"]:
        assert r["source"]["meeting_id"] == MEETING_ID


def test_search_no_chunks_file_controlled_unavailable(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path, chunks_exist=False)
    resp = client.post(f"/meetings/{MEETING_ID}/search", json={"query": "бюджет"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["results"] == []


def test_search_empty_index_returns_empty_results(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path, chunks_rows=[])
    resp = client.post(f"/meetings/{MEETING_ID}/search", json={"query": "бюджет"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["results"] == []


def test_search_no_local_paths_in_response(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/search", json={"query": "бюджет"})
    body_text = resp.text
    assert "source_path" not in body_text
    assert "/abs/local/path" not in body_text
    assert str(tmp_path) not in body_text


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------

def test_chat_unauthenticated_401(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "бюджет"},
        headers={"Authorization": ""},
    )
    assert resp.status_code == 401


def test_chat_missing_permission_403(tmp_path: Path) -> None:
    client, repo, _llm = make_client(tmp_path)
    _make_user(repo, "norights2@example.com")
    cookie, csrf = _login(client, "norights2@example.com")
    resp = client.post(
        f"/meetings/{MEETING_ID}/chat",
        json={"query": "бюджет"},
        headers={"Authorization": "", "X-CSRF-Token": csrf},  # CSRF valid → only perm fails
        cookies={"ma_session": cookie},
    )
    assert resp.status_code == 403


def test_chat_unknown_meeting_404(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post("/meetings/2099-09-09__ghost/chat", json={"query": "бюджет"})
    assert resp.status_code == 404


def test_chat_no_context_returns_refusal(tmp_path: Path) -> None:
    client, _repo, llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "zzzqqq неведомое"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] is None
    assert body["refusal"]
    assert body["citations"] == []
    assert llm.calls == []  # LLM never called without context


def test_chat_answer_uses_only_meeting_context(tmp_path: Path) -> None:
    client, _repo, llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["refusal"] is None
    # LLM prompt was built only from this meeting's chunks
    assert llm.calls, "LLM should be called when context exists"
    prompt = llm.calls[0].prompt
    assert "другой встречи" not in prompt
    assert "Глобальный проектный документ" not in prompt


def test_chat_citations_are_meeting_scoped_with_source_fields(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет"})
    body = resp.json()
    assert body["citations"]
    cited_ids = {c["chunk_id"] for c in body["citations"]}
    assert cited_ids <= {"c1", "c2"}
    for c in body["citations"]:
        assert "excerpt" in c
        assert "start_sec" in c and "end_sec" in c
        assert "speaker" in c
    assert "/abs/local/path" not in resp.text


def test_chat_citations_filtered_to_actually_cited_sources(tmp_path: Path) -> None:
    """Answer citing only [S2] must return only that source, not all retrieved."""
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("Бюджет увеличен [S2]."))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()
    # Query matches c1 and c2, but the answer only references [S2] → c2.
    assert body["citations_basis"] == "cited"
    assert len(body["citations"]) == 1
    assert body["citations"][0]["chunk_id"] == "c2"


def test_chat_citations_include_all_referenced_sources(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("Итог [S1] и ещё [S2]."))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    body = resp.json()
    assert body["citations_basis"] == "cited"
    assert {c["chunk_id"] for c in body["citations"]} == {"c1", "c2"}


def test_chat_no_markers_falls_back_to_retrieved(tmp_path: Path) -> None:
    """When the model emits no [S#] markers, surface retrieved sources but label them."""
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("Ответ без ссылок на источники."))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    body = resp.json()
    assert body["citations_basis"] == "retrieved"
    assert {c["chunk_id"] for c in body["citations"]} == {"c1", "c2"}


def test_chat_hallucinated_citation_index_is_dropped(tmp_path: Path) -> None:
    """A reference to a source that was never provided ([S9]) must not be honored."""
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("Согласно [S9] всё хорошо."))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    body = resp.json()
    # No valid in-range markers → fall back to retrieved (cannot trust [S9]).
    assert body["citations_basis"] == "retrieved"
    cited_ids = {c["chunk_id"] for c in body["citations"]}
    assert cited_ids <= {"c1", "c2"}


def test_chat_citations_preserve_answer_citation_order(tmp_path: Path) -> None:
    """Citations must appear in the order the answer cites them, not ranked order.

    The answer cites [S2] before [S1].  The ranked list has c1 as S1 and c2 as S2.
    The returned citations should be [c2, c1], not [c1, c2].
    """
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("Важно [S2], дополнительно [S1]."))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет", "top_k": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["citations_basis"] == "cited"
    assert len(body["citations"]) == 2
    assert body["citations"][0]["chunk_id"] == "c2"
    assert body["citations"][1]["chunk_id"] == "c1"


def test_cited_source_indices_parsing() -> None:
    from asu_june_bot.meetings.qa import _cited_source_indices

    assert _cited_source_indices("a [S1] b [S3] c [S1]", 5) == [1, 3]
    assert _cited_source_indices("lower [s2] case", 5) == [2]
    assert _cited_source_indices("out [S9] of range", 3) == []
    assert _cited_source_indices("no markers here", 5) == []
    assert _cited_source_indices("", 5) == []


def test_chat_refusal_payload_has_null_citations_basis(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "zzzqqq неведомое"})
    body = resp.json()
    assert body["citations"] == []
    assert body["citations_basis"] is None


def test_chat_llm_unavailable_controlled_response(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path, llm=FailingLLM())
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] is None
    assert body["refusal"]  # controlled, generic message
    assert "provider down" not in resp.text  # no backend error leaked


def test_chat_malformed_short_llm_fragment_returns_no_answer(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path, llm=FakeLLM("На"))
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "no_answer"
    assert body["answer"] is None
    assert body["refusal"]
    assert body["citations"] == []
    assert body["citations_basis"] is None


# ------------------------------------------------------------------
# Workspace UI
# ------------------------------------------------------------------

def test_workspace_qa_placeholder_replaced(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text
    assert "qa-placeholder" not in body
    assert "coming soon" not in body.lower()
    assert 'id="qa-question"' in body
    assert 'id="qa-ask-btn"' in body
    assert 'id="qa-search-input"' in body


def test_workspace_qa_no_unsafe_inline_handlers(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    # No inline JS handlers wired to Q&A actions
    assert 'onclick="askQuestion' not in body
    assert 'onclick="meetingSearch' not in body
    # Dynamic answer/citation text is set via textContent, not innerHTML interpolation
    assert "setText(" in body
    assert "addEventListener" in body


def test_workspace_qa_citations_use_data_attrs_and_listeners(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "dataset.startSec" in body
    assert "qa-citation" in body
    assert "qa-result" in body


def test_workspace_qa_no_browser_storage_for_answers(tmp_path: Path) -> None:
    client, _repo, _llm = make_client(tmp_path)
    body = client.get(f"/meetings/{MEETING_ID}/workspace").text + load_ui_asset("workspace.js")
    assert "localStorage" not in body
    assert "sessionStorage" not in body


# ------------------------------------------------------------------
# _artifact_ref safety — path traversal / absolute path regression
# ------------------------------------------------------------------

def test_search_does_not_expose_absolute_relative_path(tmp_path: Path) -> None:
    rows = [dict(CHUNK_ROWS[0], relative_path="/abs/local/path/secret.jsonl")]
    client, _repo, _llm = make_client(tmp_path, chunks_rows=rows)
    resp = client.post(f"/meetings/{MEETING_ID}/search", json={"query": "бюджет"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"]
    assert body["results"][0]["source"]["artifact"] is None
    assert "/abs/local/path" not in resp.text


def test_chat_does_not_expose_traversal_relative_path(tmp_path: Path) -> None:
    rows = [dict(CHUNK_ROWS[0], relative_path="../secret.jsonl")]
    client, _repo, _llm = make_client(tmp_path, chunks_rows=rows)
    resp = client.post(f"/meetings/{MEETING_ID}/chat", json={"query": "бюджет"})
    assert resp.status_code == 200
    assert "../secret" not in resp.text
