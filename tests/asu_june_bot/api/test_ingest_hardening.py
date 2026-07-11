from __future__ import annotations

import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import asu_june_bot.api.routes_ingest as ingest_routes  # noqa: E402
from asu_june_bot.api.app import create_app  # noqa: E402
from asu_june_bot.api.routes_ingest import (  # noqa: E402
    UploadBufferError,
    UploadTooLargeError,
    _buffer_upload,
)
from asu_june_bot.auth.repository import AuthRepository  # noqa: E402
from asu_june_bot.auth.service import LocalAuthService  # noqa: E402
from asu_june_bot.auth.throttle import LoginThrottle  # noqa: E402
from asu_june_bot.meetings.service import MeetingsService  # noqa: E402

TOKEN = "ingest-hardening-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PRIVATE_ERROR = r"C:\Users\Private\temp\upload.bin"


@dataclass(slots=True)
class FakeState:
    meetings_service: MeetingsService
    local_auth_service: LocalAuthService
    login_throttle: LoginThrottle = field(default_factory=LoginThrottle)


def _client(root: Path, service: MeetingsService | None = None) -> tuple[TestClient, MeetingsService]:
    repository = AuthRepository(root / "_auth.db")
    repository.initialize()
    meetings_service = service or MeetingsService(root)
    app = create_app()
    app.state.asu_june_bot = FakeState(
        meetings_service=meetings_service,
        local_auth_service=LocalAuthService(repository),
    )
    return TestClient(app, raise_server_exceptions=False), meetings_service


def _put_temp_files_under(
    monkeypatch: pytest.MonkeyPatch,
    temp_root: Path,
) -> None:
    temp_root.mkdir(parents=True, exist_ok=True)
    original = ingest_routes.tempfile.NamedTemporaryFile

    def _named_temp(*args, **kwargs):
        kwargs["dir"] = temp_root
        return original(*args, **kwargs)

    monkeypatch.setattr(ingest_routes.tempfile, "NamedTemporaryFile", _named_temp)


def test_oversized_upload_returns_413_before_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = _client(tmp_path, MeetingsService(tmp_path, max_upload_bytes=4))

    response = client.post(
        "/meetings/ingest",
        files={"file": ("large.mp3", b"12345", "audio/mpeg")},
        headers=AUTH,
    )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "error": "upload_too_large",
        "message": "Uploaded file exceeds the configured size limit",
        "max_bytes": 4,
    }
    assert not [path for path in tmp_path.iterdir() if path.is_dir()]


def test_upload_exactly_at_limit_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = _client(tmp_path, MeetingsService(tmp_path, max_upload_bytes=4))

    response = client.post(
        "/meetings/ingest",
        files={"file": ("exact.mp3", b"1234", "audio/mpeg")},
        headers=AUTH,
    )

    assert response.status_code == 201


def test_streaming_oversize_removes_partial_temp(tmp_path: Path, monkeypatch) -> None:
    temp_root = tmp_path / "temp"
    _put_temp_files_under(monkeypatch, temp_root)
    upload = SimpleNamespace(file=io.BytesIO(b"12345"))

    with pytest.raises(UploadTooLargeError):
        _buffer_upload(upload, suffix=".mp3", max_bytes=4)  # type: ignore[arg-type]

    assert not list(temp_root.glob("meetingagent-ingest-*"))


def test_interrupted_stream_removes_partial_temp(tmp_path: Path, monkeypatch) -> None:
    temp_root = tmp_path / "temp"
    _put_temp_files_under(monkeypatch, temp_root)

    class InterruptingStream:
        calls = 0

        def read(self, _size: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise KeyboardInterrupt

    upload = SimpleNamespace(file=InterruptingStream())

    with pytest.raises(KeyboardInterrupt):
        _buffer_upload(upload, suffix=".wav", max_bytes=100)  # type: ignore[arg-type]

    assert not list(temp_root.glob("meetingagent-ingest-*"))


def test_successful_request_removes_buffer_temp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    temp_root = tmp_path / "temp"
    _put_temp_files_under(monkeypatch, temp_root)
    client, _ = _client(tmp_path)

    response = client.post(
        "/meetings/ingest",
        files={"file": ("ok.wav", b"RIFF-test", "audio/wav")},
        headers=AUTH,
    )

    assert response.status_code == 201
    assert not list(temp_root.glob("meetingagent-ingest-*"))


def test_buffer_error_does_not_expose_internal_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = _client(tmp_path)

    def _fail(*_args, **_kwargs):
        raise UploadBufferError(PRIVATE_ERROR)

    monkeypatch.setattr(ingest_routes, "_buffer_upload", _fail)
    response = client.post(
        "/meetings/ingest",
        files={"file": ("error.mp3", b"content", "audio/mpeg")},
        headers=AUTH,
    )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "upload_buffer_failed"
    assert PRIVATE_ERROR not in response.text


def test_create_error_does_not_expose_internal_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, service = _client(tmp_path)

    def _fail(**_kwargs):
        raise OSError(PRIVATE_ERROR)

    monkeypatch.setattr(service, "create_deduplicated_meeting", _fail)
    response = client.post(
        "/meetings/ingest",
        files={"file": ("error.mp3", b"content", "audio/mpeg")},
        headers=AUTH,
    )

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "meeting_create_failed"
    assert PRIVATE_ERROR not in response.text


@pytest.mark.parametrize(
    ("filename", "title"),
    [
        ("a" * 256 + ".mp3", None),
        ("meeting.mp3", "x" * 501),
        ("bad:name.mp3", None),
    ],
)
def test_upload_metadata_is_bounded(
    tmp_path: Path,
    monkeypatch,
    filename: str,
    title: str | None,
) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client, _ = _client(tmp_path)
    data = {"title": title} if title is not None else None

    response = client.post(
        "/meetings/ingest",
        files={"file": (filename, b"content", "audio/mpeg")},
        data=data,
        headers=AUTH,
    )

    assert response.status_code == 422
    assert not [path for path in tmp_path.iterdir() if path.is_dir()]


def test_concurrent_identical_uploads_create_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEETINGAGENT_API_TOKEN", TOKEN)
    client_one, _ = _client(tmp_path, MeetingsService(tmp_path))
    client_two, _ = _client(tmp_path, MeetingsService(tmp_path))
    barrier = threading.Barrier(2)
    content = b"same concurrent recording"

    def _upload(client: TestClient):
        barrier.wait(timeout=5)
        return client.post(
            "/meetings/ingest",
            files={"file": ("same.mp3", content, "audio/mpeg")},
            headers=AUTH,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(_upload, (client_one, client_two)))

    assert sorted(response.status_code for response in responses) == [201, 409]
    created = next(response for response in responses if response.status_code == 201)
    duplicate = next(response for response in responses if response.status_code == 409)
    assert duplicate.json()["existing_meeting_id"] == created.json()["meeting_id"]
    meeting_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(meeting_dirs) == 1
    assert (meeting_dirs[0] / "meeting.json").exists()
