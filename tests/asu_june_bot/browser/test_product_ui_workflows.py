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
from urllib.parse import urlparse

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
from asu_june_bot.api.routes_meetingagent_ui import router as meetingagent_router  # noqa: E402
from asu_june_bot.api.routes_workspace import router as workspace_router  # noqa: E402
from asu_june_bot.api.ui_assets import UI_ASSETS_V1_DIR  # noqa: E402


MEETING_ID = "2026-07-12__browser-smoke"


def _build_ui_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_context_middleware)
    app.mount(
        "/assets/v1",
        StaticFiles(directory=UI_ASSETS_V1_DIR, check_dir=True),
        name="ui-assets-v1",
    )
    app.include_router(meetingagent_router)
    app.include_router(workspace_router)
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
    expect(page.locator("#authStatus")).to_contain_text("admin@local")

    page.locator("#showUploadBtn").click()
    page.locator("#meetingFile").set_input_files(
        {"name": "smoke.mp4", "mimeType": "video/mp4", "buffer": b"browser-smoke"}
    )
    page.locator("#meetingTitle").fill("Browser smoke")
    page.locator("#postUploadAction").select_option("none")
    page.locator("#asrEngine").select_option("gigaam")
    page.locator("#uploadSubmit").click()

    expect(page.locator("#message")).to_contain_text("карточка встречи создана")
    expect(page.locator("#uploadResult")).to_contain_text(MEETING_ID)
    upload_headers = captured["upload_headers"]
    assert isinstance(upload_headers, dict)
    assert upload_headers.get("x-csrf-token") == "browser-csrf"
    assert str(upload_headers.get("content-type", "")).startswith("multipart/form-data")

    page.get_by_role("button", name="Запустить транскрибацию").click()
    expect(page.locator("#message")).to_contain_text("Pipeline запущен")
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
    expect(page.locator("#speaker-map-status")).to_have_text("Saved")
    assert captured["mapping"] == {
        "mapping": {"SPEAKER_01": {"name": "Иван Петров", "role": "Руководитель"}}
    }
    mapping_headers = captured["mapping_headers"]
    assert isinstance(mapping_headers, dict)
    assert mapping_headers.get("x-csrf-token") == "workspace-csrf"
    expect(page.locator("#transcript-list")).to_contain_text("Иван Петров")

    page.get_by_role("button", name="View").click()
    expect(page.locator("#artifact-viewer")).to_contain_text("Итог встречи")

    page.locator("#qa-question").fill("Какой срок согласовали?")
    page.locator("#qa-ask-btn").click()
    expect(page.locator("#qa-answer")).to_have_text("Срок поставки согласован.")
    expect(page.locator("#qa-citations")).to_contain_text("[00:00:12, SPEAKER_01]")
    assert captured["chat"] == {"query": "Какой срок согласовали?", "top_k": 5}

    page.locator("#qa-search-input").fill("срок поставки")
    page.locator("#qa-search-btn").click()
    expect(page.locator("#qa-search-results")).to_contain_text("Согласовали срок поставки")
    expect(page.locator("#qa-search-mode")).to_have_text("retrieval: lexical")
    assert captured["search"] == {"query": "срок поставки", "top_k": 5}

    page.get_by_role("button", name="Run full pipeline").click()
    expect(page.locator("#jobs-error")).to_be_hidden()
    assert captured["pipeline"] == {"profile": "full", "resume": False, "force": False}
    pipeline_headers = captured["pipeline_headers"]
    assert isinstance(pipeline_headers, dict)
    assert pipeline_headers.get("x-csrf-token") == "workspace-csrf"
    assert errors == []
