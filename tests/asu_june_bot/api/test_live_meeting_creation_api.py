from __future__ import annotations

import json
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient

from asu_june_bot.api.app import create_app
from asu_june_bot.auth.repository import AuthRepository
from asu_june_bot.auth.service import AdminService, LocalAuthService
from asu_june_bot.auth.throttle import LoginThrottle
from asu_june_bot.meetings.service import MeetingsService


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "configs" / "schemas" / "meeting.schema.json"


def _process_create_live(
    meetings_root: str,
    start_event,
    result_queue,
) -> None:
    service = MeetingsService(Path(meetings_root))
    start_event.wait(timeout=10)
    try:
        card = service.create_live_meeting(
            title="Process race",
            meeting_date="2026-07-14",
            language="ru",
        )
        result_queue.put(("ok", card["meeting_id"]))
    except Exception as exc:  # pragma: no cover - reported to the parent
        result_queue.put(("error", type(exc).__name__))


class _Runner:
    def live_session_active(self, _meeting_id: str) -> bool:
        return False

    def recovery_summary(self, _meeting_id: str) -> dict[str, object]:
        return {"state": "clean", "recovered_jobs": 0}

    def worker_runtime_error(
        self,
        _stage: str,
        _options: dict[str, object] | None = None,
    ) -> None:
        return None


@dataclass(slots=True)
class _State:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService
    admin_service: AdminService
    job_runner: _Runner = field(default_factory=_Runner)
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)
    trusted_proxy_cidrs: list[str] = field(default_factory=list)


def _build_app(tmp_path: Path) -> tuple[TestClient, AdminService, MeetingsService]:
    repository = AuthRepository(tmp_path / "auth.db")
    repository.initialize()
    local_auth = LocalAuthService(repository)
    admin = AdminService(repository)
    service = MeetingsService(tmp_path / "meetings")
    app = create_app(config={})
    app.state.asu_june_bot = _State(
        meetings_service=service,
        local_auth_service=local_auth,
        admin_service=admin,
    )
    return TestClient(app, raise_server_exceptions=False), admin, service


def _login(
    client: TestClient,
    admin: AdminService,
    *,
    email: str,
    roles: list[str],
) -> str:
    admin.create_user(
        email=email,
        password="StrongPassword!123",
        roles=roles,
        actor_id="system",
    )
    response = client.post(
        "/auth/local/login",
        json={"email": email, "password": "StrongPassword!123"},
    )
    assert response.status_code == 200, response.json()
    return str(response.json()["csrf_token"])


def test_editor_creates_schema_valid_live_card_and_reads_product_surfaces(
    tmp_path: Path,
) -> None:
    client, admin, service = _build_app(tmp_path)
    csrf = _login(client, admin, email="editor@example.test", roles=["editor"])

    created = client.post(
        "/meetings/live",
        json={"title": "  Weekly   status  ", "date": "2026-07-14", "language": "ru"},
        headers={"X-CSRF-Token": csrf},
    )

    assert created.status_code == 201, created.json()
    body = created.json()
    meeting_id = body["meeting_id"]
    assert meeting_id == "2026-07-14__weekly-status"
    assert body == {
        "meeting_id": meeting_id,
        "title": "Weekly status",
        "date": "2026-07-14",
        "language": "ru",
        "source_kind": "live_session",
        "workspace_url": f"/meetings/{meeting_id}/workspace",
    }

    meeting_dir = service.root / meeting_id
    card = json.loads((meeting_dir / "meeting.json").read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(card)
    assert card["source"] == {
        "kind": "live_session",
        "audio_tracks": ["MIC", "SYS"],
        "derived_tracks": ["MIX"],
    }
    assert card["artifacts"] == {}
    assert card["rag"]["indexed_artifacts"] == []
    assert card["rag"]["no_index_artifacts"] == []
    assert not (meeting_dir / "source").exists()

    listing = client.get("/meetings?limit=20")
    detail = client.get(f"/meetings/{meeting_id}")
    readiness = client.get(f"/meetings/{meeting_id}/pipeline/readiness")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["source_kind"] == "live_session"
    assert listing.json()["items"][0]["media_count"] == 0
    assert detail.status_code == 200
    assert detail.json()["language"] == "ru"
    assert detail.json()["source"]["kind"] == "live_session"
    assert readiness.status_code == 200
    stages = {item["stage"]: item for item in readiness.json()["stages"]}
    assert stages["extract_audio"]["reason"] == "source_media_missing"
    assert stages["transcribe"]["reason"] == "audio_missing"


def test_viewer_cannot_create_live_meeting(tmp_path: Path) -> None:
    client, admin, service = _build_app(tmp_path)
    csrf = _login(client, admin, email="viewer@example.test", roles=["viewer"])

    response = client.post(
        "/meetings/live",
        json={"title": "Viewer attempt"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 403
    assert not service.root.exists()


def test_editor_cookie_request_requires_csrf(tmp_path: Path) -> None:
    client, admin, service = _build_app(tmp_path)
    _login(client, admin, email="editor@example.test", roles=["editor"])

    response = client.post("/meetings/live", json={"title": "No CSRF"})

    assert response.status_code == 403
    assert not service.root.exists()


def test_live_meeting_validation_is_bounded_and_does_not_create_card(tmp_path: Path) -> None:
    client, admin, service = _build_app(tmp_path)
    csrf = _login(client, admin, email="editor@example.test", roles=["editor"])

    whitespace = client.post(
        "/meetings/live",
        json={"title": "   "},
        headers={"X-CSRF-Token": csrf},
    )
    language = client.post(
        "/meetings/live",
        json={"title": "Bad language", "language": "../../private"},
        headers={"X-CSRF-Token": csrf},
    )
    bad_date = client.post(
        "/meetings/live",
        json={"title": "Bad date", "date": "2026-99-99"},
        headers={"X-CSRF-Token": csrf},
    )

    assert whitespace.status_code == 422
    assert whitespace.json()["detail"]["error"] == "invalid_meeting_metadata"
    assert language.status_code == 422
    assert language.json()["detail"]["error"] == "invalid_meeting_metadata"
    assert bad_date.status_code == 422
    assert "../../private" not in json.dumps(language.json())
    assert not service.root.exists() or not [
        path for path in service.root.iterdir() if path.is_dir()
    ]


def test_concurrent_live_creation_allocates_unique_cards_without_overwrite(
    tmp_path: Path,
) -> None:
    service = MeetingsService(tmp_path / "meetings")
    barrier = threading.Barrier(8)

    def _create(_index: int) -> dict[str, object]:
        barrier.wait(timeout=10)
        return service.create_live_meeting(
            title="Concurrent live",
            meeting_date="2026-07-14",
            language="ru",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        cards = list(pool.map(_create, range(8)))

    ids = [str(card["meeting_id"]) for card in cards]
    assert len(ids) == len(set(ids)) == 8
    for meeting_id in ids:
        stored = json.loads(
            (service.root / meeting_id / "meeting.json").read_text(encoding="utf-8")
        )
        assert stored["meeting_id"] == meeting_id
        assert stored["title"] == "Concurrent live"
    assert not list(service.root.glob(".live-card-*"))


def test_live_creation_keeps_existing_card_on_collision(tmp_path: Path) -> None:
    service = MeetingsService(tmp_path / "meetings")
    first = service.create_live_meeting(
        title="Collision",
        meeting_date="2026-07-14",
        language="ru",
    )
    first_path = service.root / str(first["meeting_id"]) / "meeting.json"
    original = first_path.read_bytes()

    second = service.create_live_meeting(
        title="Collision",
        meeting_date="2026-07-14",
        language="en",
    )

    assert second["meeting_id"] == "2026-07-14__collision-2"
    assert first_path.read_bytes() == original


def test_concurrent_processes_publish_distinct_complete_live_cards(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    meetings_root = tmp_path / "meetings"
    processes = [
        context.Process(
            target=_process_create_live,
            args=(str(meetings_root), start_event, result_queue),
        )
        for _ in range(4)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = [result_queue.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    assert all(status == "ok" for status, _value in results), results
    ids = [str(value) for _status, value in results]
    assert len(ids) == len(set(ids)) == 4
    for meeting_id in ids:
        card_path = meetings_root / meeting_id / "meeting.json"
        assert card_path.exists()
        assert json.loads(card_path.read_text(encoding="utf-8"))["meeting_id"] == meeting_id
    assert not list(meetings_root.glob(".live-card-*"))
