"""Chromium smoke tests for the two supported product UI workflows.

The browser loads the production templates, versioned assets and CSP from a
real local ASGI server. API responses are deterministic and intercepted in the
browser so the suite never invokes ASR, embeddings or an LLM.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, Route, expect, sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.middleware import request_context_middleware  # noqa: E402
from asu_june_bot.api.routes_admin_ui import (  # noqa: E402
    require_admin_page,
    router as admin_ui_router,
)
from asu_june_bot.api.routes_meetingagent_ui import router as meetingagent_router  # noqa: E402
from asu_june_bot.api.routes_workspace import router as workspace_router  # noqa: E402
from asu_june_bot.api.ui_assets import UI_ASSETS_V1_DIR, UI_ASSETS_V2_DIR  # noqa: E402


MEETING_ID = "2026-07-12__browser-smoke"


def _build_ui_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    app.mount(
        "/assets/v1",
        StaticFiles(directory=UI_ASSETS_V1_DIR, check_dir=True),
        name="ui-assets-v1",
    )
    app.mount(
        "/assets/v2",
        StaticFiles(directory=UI_ASSETS_V2_DIR, check_dir=True),
        name="ui-assets-v2",
    )
    app.include_router(meetingagent_router)
    app.include_router(workspace_router)
    app.include_router(admin_ui_router)
    app.dependency_overrides[require_admin_page] = lambda: object()
    return app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def ui_base_url() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(
        _build_ui_app(),
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
        ws="none",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/MeetingAgent", timeout=0.5) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("UI test server did not start")
    yield base_url
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "UI test server did not stop"


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    instance = context.new_page()
    yield instance
    context.close()


def _fulfill_json(route: Route, payload: object, *, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload, ensure_ascii=False),
    )


def _capture_browser_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    return errors


def test_meetingagent_upload_and_pipeline_workflow(page: Page, ui_base_url: str) -> None:
    captured: dict[str, object] = {}
    meetings: list[dict[str, object]] = []

    def handle_api(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if path == "/auth/me":
            _fulfill_json(
                route,
                {
                    "email": "admin@local",
                    "roles": ["admin"],
                    "permissions": ["meetings.ingest", "jobs.start"],
                },
            )
        elif path == "/auth/csrf":
            _fulfill_json(route, {"csrf_token": "browser-csrf"})
        elif path == "/meetings" and request.method == "GET":
            _fulfill_json(route, {"items": meetings})
        elif path == "/meetings/ingest" and request.method == "POST":
            captured["upload_headers"] = request.headers
            meetings[:] = [
                {
                    "meeting_id": MEETING_ID,
                    "title": "Browser smoke",
                    "date": "2026-07-12",
                    "processing_status": "new",
                    "source": {"media_files": [{"original_filename": "smoke.mp4"}]},
                }
            ]
            _fulfill_json(route, meetings[0], status=201)
        elif path == f"/meetings/{MEETING_ID}/jobs/pipeline" and request.method == "POST":
            captured["pipeline"] = json.loads(request.post_data or "{}")
            captured["pipeline_headers"] = request.headers
            _fulfill_json(route, {"job_id": "pipeline-browser-1"}, status=202)
        elif path == "/jobs/active":
            _fulfill_json(route, {})
        else:
            route.continue_()

    page.route("**/*", handle_api)
    errors = _capture_browser_errors(page)
    response = page.goto(f"{ui_base_url}/MeetingAgent", wait_until="networkidle")
    assert response is not None
    assert "script-src 'self'" in response.headers["content-security-policy"]
    expect(page.locator("#authStatus")).to_have_text("Администратор")
    expect(page.locator("#railAccount")).to_have_text("admin@local")
    expect(page.locator("#adminNav")).to_be_hidden()

    page.locator("#showUploadBtn").click()
    page.locator("#meetingFile").set_input_files(
        {"name": "smoke.mp4", "mimeType": "video/mp4", "buffer": b"browser-smoke"}
    )
    page.locator("#meetingTitle").fill("Browser smoke")
    page.locator('input[name="profile-choice"][value="none"]').check()
    page.locator("#asrEngine").select_option("gigaam")
    page.locator("#uploadSubmit").click()

    expect(page.locator("#message")).to_contain_text("Карточка встречи создана")
    expect(page.locator("#uploadResult")).to_contain_text(MEETING_ID)
    upload_headers = captured["upload_headers"]
    assert isinstance(upload_headers, dict)
    assert upload_headers.get("x-csrf-token") == "browser-csrf"
    assert str(upload_headers.get("content-type", "")).startswith("multipart/form-data")

    page.get_by_role("button", name="Запустить транскрибацию").click()
    expect(page.locator("#message")).to_contain_text("Обработка запущена")
    assert captured["pipeline"] == {"profile": "transcript_only", "asr_engine": "gigaam"}
    pipeline_headers = captured["pipeline_headers"]
    assert isinstance(pipeline_headers, dict)
    assert pipeline_headers.get("x-csrf-token") == "browser-csrf"
    assert errors == []


def test_workspace_transcript_mapping_artifacts_qa_and_pipeline(
    page: Page,
    ui_base_url: str,
) -> None:
    captured: dict[str, object] = {}
    mapping = {"SPEAKER_01": {"name": "", "role": ""}}

    def speaker_payload() -> dict[str, object]:
        values = mapping["SPEAKER_01"]
        return {
            "speakers": [
                {
                    "speaker_label": "SPEAKER_01",
                    "name": values["name"],
                    "role": values["role"],
                    "display_name": values["name"] or "SPEAKER_01",
                    "mapped": bool(values["name"] or values["role"]),
                }
            ]
        }

    def handle_api(route: Route) -> None:
        request = route.request
        path = urlparse(request.url).path
        prefix = f"/meetings/{MEETING_ID}"
        if path == "/auth/me":
            _fulfill_json(
                route,
                {
                    "email": "editor@local",
                    "permissions": [
                        "jobs.start",
                        "jobs.retry",
                        "jobs.cancel",
                        "meetings.edit",
                        "transcripts.read",
                        "artifacts.read",
                    ],
                },
            )
        elif path == "/auth/csrf":
            _fulfill_json(route, {"csrf_token": "workspace-csrf"})
        elif path == prefix:
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "title": "Workspace browser smoke",
                    "date": "2026-07-12",
                    "processing_status": "chunked",
                },
            )
        elif path == f"{prefix}/media":
            _fulfill_json(route, {"media": []})
        elif path == f"{prefix}/transcript/segments":
            display = mapping["SPEAKER_01"]["name"] or "SPEAKER_01"
            _fulfill_json(
                route,
                {
                    "segments": [
                        {
                            "segment_id": "seg-000001",
                            "start_sec": 12.0,
                            "end_sec": 15.0,
                            "speaker": display,
                            "speaker_label": "SPEAKER_01",
                            "speaker_role": mapping["SPEAKER_01"]["role"],
                            "text": "Согласовали срок поставки.",
                        }
                    ]
                },
            )
        elif path == f"{prefix}/speakers" and request.method == "GET":
            _fulfill_json(route, speaker_payload())
        elif path == f"{prefix}/speakers/mapping" and request.method == "PUT":
            body = json.loads(request.post_data or "{}")
            captured["mapping"] = body
            captured["mapping_headers"] = request.headers
            mapping.update(body["mapping"])
            _fulfill_json(route, speaker_payload())
        elif path == f"{prefix}/artifacts":
            _fulfill_json(
                route,
                {"artifacts": [{"key": "memo", "exists": True, "size_bytes": 42}]},
            )
        elif path == f"{prefix}/artifacts/memo":
            _fulfill_json(route, {"content": "Итог встречи: срок согласован."})
        elif path == f"{prefix}/jobs/stages":
            _fulfill_json(
                route,
                {
                    "stages": [
                        {"stage": "transcribe", "label": "Transcribe", "description": "ASR"},
                        {"stage": "chunk", "label": "Chunk", "description": "Chunk transcript"},
                    ]
                },
            )
        elif path == f"{prefix}/pipeline/readiness":
            _fulfill_json(
                route,
                {
                    "stages": [
                        {"stage": "transcribe", "state": "done", "can_run": False},
                        {"stage": "chunk", "state": "ready", "can_run": True},
                    ]
                },
            )
        elif path == f"{prefix}/artifacts/manifest":
            _fulfill_json(
                route,
                {
                    "artifacts": [
                        {"artifact_key": "segments", "exists": True},
                        {"artifact_key": "chunks", "exists": True},
                        {"artifact_key": "index_status", "exists": True},
                        {"artifact_key": "memo", "exists": True},
                    ]
                },
            )
        elif path == f"{prefix}/live/preflight":
            _fulfill_json(
                route,
                {
                    "source": "MIC",
                    "available": False,
                    "reason": "model_missing",
                    "model_ready": False,
                    "devices": [],
                    "devices_truncated": False,
                },
            )
        elif path == f"{prefix}/live/sessions/active":
            _fulfill_json(route, {"meeting_id": MEETING_ID, "session": None})
        elif path == f"{prefix}/live/timeline":
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "source": "MIX",
                    "timeline_started_at": None,
                    "segments": [],
                    "after": 0,
                    "next_after": 0,
                    "total": 0,
                    "truncated": False,
                    "warnings": [],
                },
            )
        elif path == f"{prefix}/live/refinement":
            source = parse_qs(urlparse(request.url).query).get("source", ["MIC"])[0]
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "source": source,
                    "state": "unavailable",
                    "can_refine": False,
                    "can_resume": False,
                    "can_force": False,
                    "reason": "live_draft_missing",
                },
            )
        elif path == "/jobs/active":
            _fulfill_json(route, {})
        elif path == f"{prefix}/jobs/pipeline" and request.method == "POST":
            captured["pipeline"] = json.loads(request.post_data or "{}")
            captured["pipeline_headers"] = request.headers
            _fulfill_json(route, {"job_id": "workspace-pipeline-1"}, status=202)
        elif path == f"{prefix}/jobs/workspace-pipeline-1":
            _fulfill_json(
                route,
                {"job_id": "workspace-pipeline-1", "meeting_id": MEETING_ID, "status": "completed"},
            )
        elif path == f"{prefix}/chat" and request.method == "POST":
            captured["chat"] = json.loads(request.post_data or "{}")
            _fulfill_json(
                route,
                {
                    "answer": "Срок поставки согласован.",
                    "retrieval_mode": "vector",
                    "citations": [
                        {
                            "citation_label": "[00:00:12, SPEAKER_01]",
                            "start_sec": 12.0,
                            "excerpt": "Согласовали срок поставки.",
                        }
                    ],
                },
            )
        elif path == f"{prefix}/search" and request.method == "POST":
            captured["search"] = json.loads(request.post_data or "{}")
            _fulfill_json(
                route,
                {
                    "retrieval_mode": "lexical",
                    "results": [
                        {
                            "text": "Согласовали срок поставки.",
                            "source": {
                                "citation_label": "[00:00:12, SPEAKER_01]",
                                "start_sec": 12.0,
                            },
                        }
                    ],
                },
            )
        else:
            route.continue_()

    page.route("**/*", handle_api)
    errors = _capture_browser_errors(page)
    response = page.goto(f"{ui_base_url}{f'/meetings/{MEETING_ID}/workspace'}", wait_until="networkidle")
    assert response is not None
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]
    expect(page.locator("#hdr-title")).to_have_text("Workspace browser smoke")
    expect(page.locator("#transcript-list")).to_contain_text("Согласовали срок поставки")

    name_input = page.locator('.speaker-map-row input[data-field="name"]')
    role_input = page.locator('.speaker-map-row input[data-field="role"]')
    name_input.fill("Иван Петров")
    role_input.fill("Руководитель")
    page.locator("#speaker-map-save-btn").click()
    expect(page.locator("#speaker-map-status")).to_have_text("Сохранено")
    assert captured["mapping"] == {
        "mapping": {"SPEAKER_01": {"name": "Иван Петров", "role": "Руководитель"}}
    }
    mapping_headers = captured["mapping_headers"]
    assert isinstance(mapping_headers, dict)
    assert mapping_headers.get("x-csrf-token") == "workspace-csrf"
    expect(page.locator("#transcript-list")).to_contain_text("Иван Петров")

    page.locator('[data-workspace-tab="artifacts"]').click()
    page.get_by_role("button", name="Открыть").click()
    expect(page.locator("#artifact-viewer")).to_contain_text("Итог встречи")

    page.locator('[data-workspace-tab="qa"]').click()
    page.locator("#qa-question").fill("Какой срок согласовали?")
    page.locator("#qa-ask-btn").click()
    expect(page.locator("#qa-answer")).to_have_text("Срок поставки согласован.")
    expect(page.locator("#qa-citations")).to_contain_text("[00:00:12, SPEAKER_01]")
    assert captured["chat"] == {"query": "Какой срок согласовали?", "top_k": 5}

    page.locator("#qa-search-input").fill("срок поставки")
    page.locator("#qa-search-btn").click()
    expect(page.locator("#qa-search-results")).to_contain_text("Согласовали срок поставки")
    expect(page.locator("#qa-search-mode")).to_have_text("поиск: лексический")
    assert captured["search"] == {"query": "срок поставки", "top_k": 5}

    page.locator('[data-workspace-tab="pipeline"]').click()
    page.get_by_role("button", name="Запустить полный цикл").click()
    expect(page.locator("#jobs-error")).to_be_hidden()
    assert captured["pipeline"] == {"profile": "full", "resume": False, "force": False}
    pipeline_headers = captured["pipeline_headers"]
    assert isinstance(pipeline_headers, dict)
    assert pipeline_headers.get("x-csrf-token") == "workspace-csrf"
    assert errors == []


def test_workspace_live_mic_start_partial_stop_and_final(
    page: Page,
    ui_base_url: str,
) -> None:
    captured: dict[str, object] = {}
    live_started = False
    live_stopped = False
    refinement_started = False
    refinement_job_polls = 0
    session_id = "live-browser-session"
    refinement_job_id = "live-refinement-job"

    def session_payload() -> dict[str, object]:
        status = "completed" if live_stopped else "running"
        return {
            "session_id": session_id,
            "meeting_id": MEETING_ID,
            "source": "MIC",
            "status": status,
            "engine": "vosk",
            "model": "vosk-model-small-ru",
            "vad": "silero",
            "created_at": "2026-07-13T12:00:00+00:00",
            "started_at": "2026-07-13T12:00:00+00:00",
            "updated_at": "2026-07-13T12:00:02+00:00",
            "finished_at": "2026-07-13T12:00:02+00:00" if live_stopped else None,
            "last_event_id": 4 if live_stopped else 2,
            "warnings": ["mic_audio_dropped"] if live_stopped else [],
            "error": None,
            "artifact_keys": ["live_segments_mic"] if live_stopped else [],
            "is_active": not live_stopped,
        }

    def handle_api(route: Route) -> None:
        nonlocal live_started, live_stopped, refinement_started, refinement_job_polls
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        query = parse_qs(parsed.query)
        prefix = f"/meetings/{MEETING_ID}"
        if path == "/auth/me":
            _fulfill_json(
                route,
                {
                    "email": "editor@local",
                    "permissions": [
                        "jobs.read",
                        "jobs.start",
                        "jobs.cancel",
                        "transcripts.read",
                        "artifacts.read",
                    ],
                },
            )
        elif path == "/auth/csrf":
            _fulfill_json(route, {"csrf_token": "live-browser-csrf"})
        elif path == prefix:
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "title": "Live browser smoke",
                    "date": "2026-07-13",
                    "processing_status": "transcribing" if live_started else "new",
                },
            )
        elif path == f"{prefix}/media":
            _fulfill_json(route, {"media": []})
        elif path == f"{prefix}/transcript/segments":
            _fulfill_json(route, {"segments": []})
        elif path == f"{prefix}/speakers":
            _fulfill_json(route, {"speakers": []})
        elif path == f"{prefix}/artifacts":
            _fulfill_json(route, {"artifacts": []})
        elif path == f"{prefix}/jobs/stages":
            _fulfill_json(route, {"stages": []})
        elif path == f"{prefix}/pipeline/readiness":
            _fulfill_json(route, {"stages": []})
        elif path == f"{prefix}/artifacts/manifest":
            _fulfill_json(route, {"artifacts": []})
        elif path == "/jobs/active":
            _fulfill_json(route, {})
        elif path == f"{prefix}/live/preflight":
            source = query.get("source", ["MIC"])[0]
            device = 7 if source == "MIC" else 12
            _fulfill_json(
                route,
                {
                    "source": source,
                    "available": True,
                    "reason": None,
                    "model_ready": True,
                    "devices": [
                        {"device_index": device, "label": f"Audio device {device}"}
                    ],
                    "devices_truncated": False,
                },
            )
        elif path == f"{prefix}/live/sessions/active":
            source = query.get("source", [""])[0]
            active = session_payload() if source == "MIC" and live_started and not live_stopped else None
            _fulfill_json(route, {"meeting_id": MEETING_ID, "session": active})
        elif path == f"{prefix}/live/timeline":
            segments = []
            if live_stopped:
                segments = [
                    {
                        "segment_id": "live-mix-mic-browser",
                        "origin_segment_id": "live-browser-final",
                        "source": "MIC",
                        "start": 0.0,
                        "end": 1.2,
                        "origin_start": 0.0,
                        "origin_end": 1.2,
                        "text": "Финальная реплика из микрофона.",
                        "confidence": None,
                    }
                ]
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "source": "MIX",
                    "timeline_started_at": "2026-07-13T12:00:00+00:00",
                    "segments": segments,
                    "after": 0,
                    "next_after": len(segments),
                    "total": len(segments),
                    "truncated": False,
                    "warnings": [],
                },
            )
        elif path == f"{prefix}/live/sessions" and request.method == "POST":
            live_started = True
            captured["start_body"] = json.loads(request.post_data or "{}")
            captured["start_headers"] = request.headers
            _fulfill_json(route, session_payload(), status=202)
        elif path == f"{prefix}/live/sessions/{session_id}" and request.method == "GET":
            _fulfill_json(route, session_payload())
        elif path == f"{prefix}/live/sessions/{session_id}/events":
            after = int(query.get("after", ["0"])[0])
            if live_stopped and after < 4:
                events = [
                    {
                        "event_id": 3,
                        "type": "final",
                        "source": "MIC",
                        "segment_id": "live-browser-final",
                        "text": "Финальная реплика из микрофона.",
                        "start": 0.0,
                        "end": 1.2,
                        "is_final": True,
                    },
                    {"event_id": 4, "type": "status", "status": "completed"},
                ]
                next_after = 4
            elif not live_stopped and after < 2:
                events = [
                    {
                        "event_id": 2,
                        "type": "partial",
                        "source": "MIC",
                        "text": "Черновая реплика",
                        "start": 0.0,
                        "end": 0.4,
                        "is_final": False,
                    }
                ]
                next_after = 2
            else:
                events = []
                next_after = after
            _fulfill_json(
                route,
                {
                    "session_id": session_id,
                    "meeting_id": MEETING_ID,
                    "source": "MIC",
                    "status": "completed" if live_stopped else "running",
                    "events": events,
                    "oldest_event_id": 1,
                    "newest_event_id": 4 if live_stopped else 2,
                    "next_after": next_after,
                    "truncated": False,
                    "partial_events_durable": False,
                },
            )
        elif path == f"{prefix}/live/sessions/{session_id}/stop" and request.method == "POST":
            live_stopped = True
            captured["stop_headers"] = request.headers
            _fulfill_json(route, session_payload())
        elif path == f"{prefix}/live/refinement" and request.method == "GET":
            source = query.get("source", ["MIC"])[0]
            if source != "MIC" or not live_stopped:
                payload = {
                    "meeting_id": MEETING_ID,
                    "source": source,
                    "state": "unavailable",
                    "can_refine": False,
                    "can_resume": False,
                    "can_force": False,
                    "reason": "live_draft_missing",
                }
            elif not refinement_started:
                payload = {
                    "meeting_id": MEETING_ID,
                    "source": source,
                    "state": "draft",
                    "can_refine": True,
                    "can_resume": False,
                    "can_force": False,
                    "live": {"engine": "vosk", "segments_count": 1, "chars_count": 35},
                }
            elif refinement_job_polls < 2:
                payload = {
                    "meeting_id": MEETING_ID,
                    "source": source,
                    "state": "refining",
                    "can_refine": False,
                    "can_resume": False,
                    "can_force": False,
                    "live": {"engine": "vosk", "segments_count": 1, "chars_count": 35},
                }
            else:
                payload = {
                    "meeting_id": MEETING_ID,
                    "source": source,
                    "state": "final",
                    "can_refine": False,
                    "can_resume": False,
                    "can_force": True,
                    "live": {"engine": "vosk", "segments_count": 1, "chars_count": 35},
                    "offline": {"engine": "faster-whisper", "model": "large-v3-turbo"},
                    "comparison": {"chars_count_delta": 12},
                }
            _fulfill_json(route, payload)
        elif path == f"{prefix}/live/refinement" and request.method == "POST":
            refinement_started = True
            captured["refinement_body"] = json.loads(request.post_data or "{}")
            captured["refinement_headers"] = request.headers
            _fulfill_json(
                route,
                {
                    "meeting_id": MEETING_ID,
                    "source": "MIC",
                    "state": "refining",
                    "job": {
                        "job_id": refinement_job_id,
                        "meeting_id": MEETING_ID,
                        "stage": "transcribe",
                        "status": "running",
                    },
                },
                status=202,
            )
        elif path == f"{prefix}/jobs/{refinement_job_id}":
            refinement_job_polls += 1
            status = "running" if refinement_job_polls < 2 else "completed"
            _fulfill_json(
                route,
                {
                    "job_id": refinement_job_id,
                    "meeting_id": MEETING_ID,
                    "stage": "transcribe",
                    "status": status,
                },
            )
        else:
            route.continue_()

    page.route("**/*", handle_api)
    errors = _capture_browser_errors(page)
    response = page.goto(
        f"{ui_base_url}/meetings/{MEETING_ID}/workspace",
        wait_until="networkidle",
    )
    assert response is not None
    page.locator('[data-workspace-tab="live"]').click()
    expect(page.locator("#live-mic-badge")).to_have_text("Готово")
    expect(page.locator("#live-sys-badge")).to_have_text("Готово")
    expect(page.locator("#live-panel")).to_contain_text("черновик и не индексируется")

    page.locator("#live-mic-start").click()
    expect(page.locator("#live-mic-badge")).to_have_text("Запись")
    expect(page.locator("#live-mic-partial")).to_have_text("Черновая реплика")
    page.locator('[data-workspace-tab="pipeline"]').click()
    expect(page.get_by_role("button", name="Запустить полный цикл")).to_be_disabled()
    page.locator('[data-workspace-tab="live"]').click()
    expect(page.locator("#live-sys-start")).to_be_enabled()
    assert captured["start_body"] == {
        "source": "MIC",
        "vad": "silero",
        "force": False,
    }
    start_headers = captured["start_headers"]
    assert isinstance(start_headers, dict)
    assert start_headers.get("x-csrf-token") == "live-browser-csrf"

    page.locator("#live-mic-stop").click()
    expect(page.locator("#live-mic-badge")).to_have_text("Завершено")
    expect(page.locator("#live-mic-partial")).to_have_text("Нет активного фрагмента")
    expect(page.locator("#live-mic-finals")).to_contain_text(
        "Финальная реплика из микрофона."
    )
    expect(page.locator("#live-mic-finals")).to_contain_text("MIC")
    expect(page.locator("#live-conversation-finals")).to_contain_text(
        "Финальная реплика из микрофона."
    )
    expect(page.locator("#live-conversation-finals")).to_contain_text("MIC")
    expect(page.locator("#live-mic-warnings")).to_contain_text("mic audio dropped")
    page.locator('[data-workspace-tab="pipeline"]').click()
    expect(page.get_by_role("button", name="Запустить полный цикл")).to_be_enabled()
    stop_headers = captured["stop_headers"]
    assert isinstance(stop_headers, dict)
    assert stop_headers.get("x-csrf-token") == "live-browser-csrf"

    page.locator('[data-workspace-tab="live"]').click()
    expect(page.locator("#live-mic-refine-badge")).to_have_text("Черновик")
    expect(page.locator("#live-mic-refine")).to_be_enabled()
    page.locator("#live-mic-refine").click()
    expect(page.locator("#live-mic-refine-badge")).to_have_text("Уточнение")
    expect(page.locator("#live-mic-refine-badge")).to_have_text("Готово", timeout=8_000)
    expect(page.locator("#live-mic-refine-summary")).to_contain_text(
        "Разница с live-черновиком: +12 символов"
    )
    assert captured["refinement_body"] == {
        "source": "MIC",
        "asr_engine": "faster-whisper",
        "force": False,
        "resume": False,
    }
    refinement_headers = captured["refinement_headers"]
    assert isinstance(refinement_headers, dict)
    assert refinement_headers.get("x-csrf-token") == "live-browser-csrf"
    assert errors == []


def test_admin_console_user_lifecycle(page: Page, ui_base_url: str) -> None:
    captured: dict[str, object] = {}
    users: list[dict[str, object]] = [
        {
            "user_id": "admin-1",
            "email": "admin@local",
            "display_name": "Administrator",
            "status": "active",
            "roles": ["admin"],
            "created_at": "2026-07-13T10:00:00+00:00",
            "updated_at": "2026-07-13T10:00:00+00:00",
            "last_login_at": "2026-07-13T10:05:00+00:00",
        },
        {
            "user_id": "viewer-1",
            "email": "viewer@local",
            "display_name": "Viewer",
            "status": "active",
            "roles": ["viewer"],
            "created_at": "2026-07-13T10:00:00+00:00",
            "updated_at": "2026-07-13T10:00:00+00:00",
            "last_login_at": None,
        },
    ]

    def handle_api(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if path == "/auth/me":
            _fulfill_json(
                route,
                {
                    "email": "admin@local",
                    "display_name": "Administrator",
                    "roles": ["admin"],
                    "permissions": ["users.manage"],
                },
            )
        elif path == "/auth/csrf":
            _fulfill_json(route, {"csrf_token": "admin-browser-csrf"})
        elif path == "/admin/security/status":
            _fulfill_json(
                route,
                {
                    "deployment_mode": "local",
                    "findings": [],
                    "error_count": 0,
                    "warning_count": 0,
                    "trusted_proxy_policy": {"configured": False, "count": 0},
                    "bootstrap_policy": {
                        "remote_allowed": False,
                        "secret_configured": False,
                        "first_admin_created": True,
                    },
                },
            )
        elif path == "/admin/users" and request.method == "GET":
            query = parse_qs(parsed.query)
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", ["25"])[0])
            _fulfill_json(
                route,
                {
                    "users": users[offset:offset + limit],
                    "total": len(users),
                    "offset": offset,
                    "limit": limit,
                },
            )
        elif path == "/admin/users" and request.method == "POST":
            payload = json.loads(request.post_data or "{}")
            captured["create"] = payload
            captured["create_headers"] = request.headers
            created = {
                "user_id": "editor-1",
                "email": payload["email"],
                "display_name": payload.get("display_name"),
                "status": "active",
                "roles": payload.get("roles", []),
                "created_at": "2026-07-13T11:00:00+00:00",
                "updated_at": "2026-07-13T11:00:00+00:00",
                "last_login_at": None,
            }
            users.append(created)
            _fulfill_json(route, created, status=201)
        elif path == "/admin/users/viewer-1" and request.method == "PATCH":
            payload = json.loads(request.post_data or "{}")
            captured["edit"] = payload
            captured["edit_headers"] = request.headers
            users[1]["display_name"] = payload["display_name"]
            users[1]["roles"] = payload["roles"]
            _fulfill_json(route, users[1])
        elif path == "/admin/users/viewer-1/disable" and request.method == "POST":
            captured["disable_headers"] = request.headers
            users[1]["status"] = "disabled"
            _fulfill_json(route, users[1])
        else:
            route.continue_()

    page.route("**/*", handle_api)
    errors = _capture_browser_errors(page)
    response = page.goto(f"{ui_base_url}/admin", wait_until="networkidle")
    assert response is not None
    assert "script-src 'self'" in response.headers["content-security-policy"]
    expect(page.locator("#session-user")).to_have_text("Administrator")
    expect(page.locator("#security-mode")).to_have_text("local")
    expect(page.locator("#users-total")).to_have_text("2 пользователей")

    page.locator("#create-user-btn").click()
    expect(page.locator("#create-user-dialog")).to_be_visible()
    page.locator("#create-email").fill("editor@local")
    page.locator("#create-display-name").fill("Editor")
    page.locator("#create-password").fill("temporary-password")
    page.locator('input[name="create-role"][value="editor"]').check()
    page.locator("#create-user-form button[type=submit]").click()
    expect(page.locator("#page-message")).to_have_text("Пользователь создан.")
    expect(page.locator("#users-total")).to_have_text("3 пользователей")
    assert captured["create"] == {
        "email": "editor@local",
        "display_name": "Editor",
        "password": "temporary-password",
        "roles": ["viewer", "editor"],
    }

    viewer_row = page.locator("#users-body tr").filter(has_text="viewer@local")
    viewer_row.get_by_role("button", name="Изменить").click()
    page.locator("#edit-display-name").fill("Project viewer")
    page.locator('input[name="edit-role"][value="editor"]').check()
    page.locator("#edit-user-form button[type=submit]").click()
    expect(page.locator("#page-message")).to_have_text("Параметры пользователя обновлены.")
    assert captured["edit"] == {
        "display_name": "Project viewer",
        "roles": ["viewer", "editor"],
    }

    viewer_row = page.locator("#users-body tr").filter(has_text="viewer@local")
    viewer_row.get_by_role("button", name="Отключить").click()
    expect(page.locator("#status-dialog")).to_be_visible()
    page.locator("#status-confirm-btn").click()
    expect(page.locator("#page-message")).to_have_text("Пользователь отключён.")
    expect(viewer_row.locator(".status")).to_have_text("disabled")

    for key in ("create_headers", "edit_headers", "disable_headers"):
        headers = captured[key]
        assert isinstance(headers, dict)
        assert headers.get("x-csrf-token") == "admin-browser-csrf"
    assert errors == []


def test_meetingagent_live_creation_opens_workspace_and_checks_sources(
    page: Page,
    ui_base_url: str,
) -> None:
    live_id = "2026-07-14__browser-live"
    prefix = f"/meetings/{live_id}"
    captured: dict[str, object] = {"preflight_sources": set()}

    def handle_api(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if path == "/auth/me":
            _fulfill_json(
                route,
                {
                    "email": "editor@local",
                    "roles": ["editor"],
                    "permissions": [
                        "meetings.upload",
                        "meetings.read",
                        "jobs.read",
                        "jobs.start",
                        "jobs.cancel",
                        "transcripts.read",
                        "artifacts.read",
                    ],
                },
            )
        elif path == "/auth/csrf":
            _fulfill_json(route, {"csrf_token": "live-browser-csrf"})
        elif path == "/meetings" and request.method == "GET":
            _fulfill_json(route, {"items": []})
        elif path == "/meetings/live" and request.method == "POST":
            captured["create_body"] = json.loads(request.post_data or "{}")
            captured["create_headers"] = request.headers
            _fulfill_json(
                route,
                {
                    "meeting_id": live_id,
                    "title": "Browser live",
                    "date": "2026-07-14",
                    "language": "ru",
                    "source_kind": "live_session",
                    "workspace_url": f"{prefix}/workspace",
                },
                status=201,
            )
        elif path == prefix:
            _fulfill_json(
                route,
                {
                    "meeting_id": live_id,
                    "title": "Browser live",
                    "date": "2026-07-14",
                    "language": "ru",
                    "processing_status": "new",
                    "source": {
                        "kind": "live_session",
                        "audio_tracks": ["MIC", "SYS"],
                        "derived_tracks": ["MIX"],
                    },
                },
            )
        elif path == f"{prefix}/media":
            _fulfill_json(route, {"media": []})
        elif path == f"{prefix}/transcript/segments":
            _fulfill_json(route, {"segments": []})
        elif path == f"{prefix}/speakers":
            _fulfill_json(route, {"speakers": []})
        elif path == f"{prefix}/artifacts":
            _fulfill_json(route, {"artifacts": []})
        elif path == f"{prefix}/jobs/stages":
            _fulfill_json(route, {"stages": []})
        elif path == f"{prefix}/pipeline/readiness":
            _fulfill_json(route, {"meeting_id": live_id, "status": "new", "stages": []})
        elif path == f"{prefix}/artifacts/manifest":
            _fulfill_json(route, {"artifacts": []})
        elif path == f"{prefix}/live/preflight":
            source = parse_qs(parsed.query).get("source", [""])[0]
            preflights = captured["preflight_sources"]
            assert isinstance(preflights, set)
            preflights.add(source)
            _fulfill_json(
                route,
                {
                    "source": source,
                    "available": False,
                    "reason": "model_missing",
                    "model_ready": False,
                    "devices": [],
                    "devices_truncated": False,
                },
            )
        elif path == f"{prefix}/live/sessions/active":
            _fulfill_json(route, {"meeting_id": live_id, "session": None})
        elif path == f"{prefix}/live/timeline":
            _fulfill_json(
                route,
                {
                    "meeting_id": live_id,
                    "source": "MIX",
                    "timeline_started_at": None,
                    "segments": [],
                    "after": 0,
                    "next_after": 0,
                    "total": 0,
                    "truncated": False,
                    "warnings": [],
                },
            )
        elif path == f"{prefix}/live/refinement":
            source = parse_qs(parsed.query).get("source", ["MIC"])[0]
            _fulfill_json(
                route,
                {
                    "meeting_id": live_id,
                    "source": source,
                    "state": "unavailable",
                    "can_refine": False,
                    "can_resume": False,
                    "can_force": False,
                    "reason": "live_draft_missing",
                },
            )
        elif path == "/jobs/active":
            _fulfill_json(route, {})
        else:
            route.continue_()

    page.route("**/*", handle_api)
    errors = _capture_browser_errors(page)
    page.goto(f"{ui_base_url}/MeetingAgent", wait_until="networkidle")
    page.locator("#showLiveBtn").click()
    page.locator("#liveMeetingTitle").fill("Browser live")
    page.locator("#liveMeetingDate").fill("2026-07-14")
    page.locator("#liveMeetingSubmit").click()

    expect(page).to_have_url(f"{ui_base_url}{prefix}/workspace")
    expect(page.locator("#hdr-title")).to_have_text("Browser live")
    page.locator('[data-workspace-tab="live"]').click()
    expect(page.locator("#live-panel-title")).to_have_text("Live-транскрибация")
    assert captured["create_body"] == {
        "title": "Browser live",
        "language": "ru",
        "date": "2026-07-14",
    }
    create_headers = captured["create_headers"]
    assert isinstance(create_headers, dict)
    assert create_headers.get("x-csrf-token") == "live-browser-csrf"
    assert captured["preflight_sources"] == {"MIC", "SYS"}
    assert errors == []
