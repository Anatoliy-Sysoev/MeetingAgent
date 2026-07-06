"""Tests for the Workspace meeting flow UI (MA-WORKSPACE-FLOW, #121).

The workspace page is server-rendered static HTML + JS; these tests freeze
the flow contract: readiness/manifest integration, pipeline/resume/retry
controls, Q&A gating, CSRF on every POST, and DOM/CSP hygiene.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asu_june_bot.api.routes_workspace import _WORKSPACE_HTML  # noqa: E402


@pytest.fixture(scope="module")
def html() -> str:
    return _WORKSPACE_HTML


# ---------------------------------------------------------------------------
# State panel: status, active job, last error, readiness, manifest
# ---------------------------------------------------------------------------

def test_state_panel_elements_present(html: str) -> None:
    assert 'id="jobs-status"' in html
    assert 'id="jobs-last-error"' in html
    assert 'id="pipeline-actions"' in html
    assert 'id="jobs-stages"' in html
    assert 'id="pipeline-results"' in html


def test_readiness_api_integrated(html: str) -> None:
    assert "/pipeline/readiness" in html
    assert "loadReadiness" in html
    assert "ready_for_retry" in html


def test_manifest_api_integrated(html: str) -> None:
    assert "/artifacts/manifest" in html
    assert "loadManifest" in html


def test_speaker_mapping_panel_integrated(html: str) -> None:
    assert 'id="speaker-map-panel"' in html
    assert 'id="speaker-map-save-btn"' in html
    assert "/speakers" in html
    assert "/speakers/mapping" in html
    assert "loadSpeakerMapping" in html
    assert "saveSpeakerMapping" in html


def test_last_error_shown_public_safe(html: str) -> None:
    # last error text comes from readiness detail (public-safe), via textContent
    assert "jobs-last-error" in html
    block = html[html.index("const lastErrEl"):]
    block = block[: block.index("renderPipelineActions()")]
    assert "textContent" in block
    assert "innerHTML" not in block


# ---------------------------------------------------------------------------
# Pipeline actions: run full / resume / retry failed
# ---------------------------------------------------------------------------

def test_run_full_pipeline_button(html: str) -> None:
    assert "Run full pipeline" in html
    assert 'profile: "full"' in html


def test_resume_button_only_for_partial_pipeline(html: str) -> None:
    assert "Resume pipeline" in html
    block = html[html.index("function renderPipelineActions"):]
    block = block[: block.index("function renderResults")]
    # resume rendered only when some stages are done AND some pending
    assert "anyDone && anyPending" in block
    assert "resume: true" in block


def test_retry_button_only_when_failed_stage(html: str) -> None:
    assert "Retry failed stage" in html
    block = html[html.index("function renderPipelineActions"):]
    block = block[: block.index("function renderResults")]
    assert "_failedStage" in block


def test_force_rerun_is_explicit_not_default(html: str) -> None:
    # done stages get an explicit "Force rerun" control, not a default Start
    assert "Force rerun" in html
    assert "retryStage(forceBtn.dataset.stage, true)" in html
    # plain retry and pipeline start never pass force implicitly
    assert "retryStage(retryBtn.dataset.stage, false)" in html


def test_blocked_stage_start_disabled(html: str) -> None:
    block = html[html.index("const blocked = ready"):]
    block = block[: block.index("row.append(info, actions)")]
    assert "startBtn.disabled = !canStart || blocked" in block


# ---------------------------------------------------------------------------
# API integration endpoints
# ---------------------------------------------------------------------------

def test_all_flow_endpoints_wired(html: str) -> None:
    assert "/jobs/pipeline" in html
    assert "/retry" in html
    assert "/cancel" in html
    assert "/jobs/stages" in html
    assert "/jobs/active" in html


# ---------------------------------------------------------------------------
# Post-completion UX
# ---------------------------------------------------------------------------

def test_results_chips_for_ready_artifacts(html: str) -> None:
    block = html[html.index("function renderResults"):]
    block = block[: block.index("function updateQaAvailability")]
    for key in ("segments", "speaker_transcript", "memo", "protocol", "tasks"):
        assert f'"{key}"' in block
    assert "entry.exists" in block


def test_panels_refresh_after_job_finishes(html: str) -> None:
    block = html[html.index("async function refreshJobs"):]
    block = block[: block.index("function startPolling")]
    assert "hadActive && _activeJob === null" in block
    assert "loadTranscript()" in block
    assert "loadArtifacts()" in block


def test_qa_gated_on_index(html: str) -> None:
    assert 'id="qa-availability"' in html
    block = html[html.index("function updateQaAvailability"):]
    assert 'manifestEntry("index_status")' in block
    assert 'manifestEntry("chunks")' in block
    assert "askBtn.disabled = !available" in block
    assert "searchBtn.disabled = !available" in block


# ---------------------------------------------------------------------------
# Security: CSRF on every POST, DOM hygiene, no absolute paths
# ---------------------------------------------------------------------------

def test_every_post_sends_csrf(html: str) -> None:
    # every fetch with method POST must carry X-CSRF-Token, either inline in
    # the headers literal or via a prepared `headers` object built with csrf
    for m in re.finditer(r'method:\s*"POST"', html):
        context = html[max(0, m.start() - 400): m.start() + 300]
        assert "X-CSRF-Token" in context, context


def test_pipeline_and_retry_posts_use_ensure_csrf(html: str) -> None:
    for fn in ("startPipeline", "retryStage", "startStage", "cancelActiveJob"):
        block = html[html.index(f"async function {fn}"):]
        block = block[: block.index("\n}\n") + 2]
        assert "ensureCsrf()" in block, fn


def test_speaker_mapping_put_uses_csrf_and_aborts_without_token(html: str) -> None:
    block = html[html.index("async function saveSpeakerMapping"):]
    block = block[: block.index("\n}\n") + 2]
    csrf_check = block.index("if (!csrf)")
    put_call = block.index('method: "PUT"')
    assert "ensureCsrf()" in block
    assert "X-CSRF-Token" in block
    assert csrf_check < put_call


def test_no_inline_event_handlers(html: str) -> None:
    assert not re.search(r"<[^>]+\son(click|change|submit|keydown|input)\s*=", html)


def test_dynamic_values_use_dom_apis(html: str) -> None:
    # new flow rendering functions must not build HTML strings
    for fn in ("renderPipelineActions", "renderResults", "updateQaAvailability", "loadSpeakerMapping"):
        block = html[html.index(f"function {fn}"):]
        block = block[: block.index("\n}\n") + 2]
        assert "innerHTML" not in block, fn


def test_no_web_storage(html: str) -> None:
    assert "localStorage" not in html
    assert "sessionStorage" not in html


# ---------------------------------------------------------------------------
# Review follow-ups (#121): tracked job polling, pipeline-aware activity,
# meetingSearch CSRF guard
# ---------------------------------------------------------------------------

def _fn_block(html: str, name: str) -> str:
    block = html[html.index(f"async function {name}")]
    block = html[html.index(f"async function {name}"):]
    return block[: block.index("\n}\n") + 2]


def test_started_jobs_track_job_id_from_202(html: str) -> None:
    for fn in ("startStage", "startPipeline", "retryStage"):
        block = _fn_block(html, fn)
        assert "_trackedJobId = started.job_id" in block, fn


def test_active_job_polls_tracked_job_endpoint(html: str) -> None:
    block = _fn_block(html, "loadActiveJob")
    # poll the specific job first — /meetings/{id}/jobs/{job_id}
    assert "/jobs/${encodeURIComponent(_trackedJobId)}" in block
    # /jobs/active is only the fallback discovery path
    assert block.index("_trackedJobId") < block.index('"/jobs/active"')


def test_pipeline_aggregate_counts_as_active(html: str) -> None:
    block = html[html.index("function _jobIsActive"):]
    block = block[: block.index("async function loadActiveJob")]
    assert 'j.status === "running"' in block
    # renderJobs shows the pipeline kind and its current stage
    assert '_activeJob.kind === "pipeline"' in html
    assert "_activeJob.current_stage" in html


def test_tracked_job_cleared_when_finished(html: str) -> None:
    block = _fn_block(html, "loadActiveJob")
    assert "_trackedJobId = null" in block


def test_meeting_search_aborts_without_csrf(html: str) -> None:
    block = _fn_block(html, "meetingSearch")
    csrf_check = block.index("if (!csrf)")
    post_call = block.index('method: "POST"')
    assert csrf_check < post_call, "CSRF guard must precede the POST"
    guard = block[csrf_check: block.index("let resp")]
    assert "return" in guard
