from __future__ import annotations

import json as _json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from asu_june_bot.meetings.service import MeetingsService, _safe_meeting_id

router = APIRouter(tags=["workspace"])

_WORKSPACE_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Meeting Workspace</title>
  <style>
    :root {
      --bg: #f3f5f7;
      --surface: #ffffff;
      --line: #dfe5eb;
      --text: #1f2933;
      --muted: #6b7785;
      --primary: #42aeea;
      --primary-strong: #168ccc;
      --primary-soft: #e7f5fd;
      --danger: #e85a70;
      --ok: #1f9d68;
      --warn: #f59e0b;
      --active-seg: #fff8e1;
      --active-seg-border: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
    }
    a { color: var(--primary-strong); }
    button {
      cursor: pointer;
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: 4px;
      padding: 4px 12px;
      font: inherit;
    }
    button:hover { background: var(--primary-soft); border-color: var(--primary); }
    button.primary {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary-strong);
    }
    button.primary:hover { background: var(--primary-strong); }

    /* ---- header ---- */
    .header {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .header .back { font-size: 18px; text-decoration: none; color: var(--muted); }
    .header .back:hover { color: var(--primary-strong); }
    .header .title { font-size: 16px; font-weight: bold; flex: 1; }
    .header .meta { font-size: 12px; color: var(--muted); }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      background: #e2e8f0;
      color: #4a5568;
    }
    .badge.ok { background: #d1fae5; color: #065f46; }
    .badge.warn { background: #fef3c7; color: #92400e; }
    .badge.err { background: #fee2e2; color: #991b1b; }

    /* ---- main grid ---- */
    .workspace {
      display: grid;
      grid-template-columns: 380px 1fr;
      grid-template-rows: auto 1fr;
      gap: 12px;
      padding: 12px 20px;
      max-width: 1400px;
      margin: 0 auto;
    }

    /* ---- panels ---- */
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      overflow: hidden;
    }
    .panel-header {
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
      font-weight: bold;
      font-size: 12px;
      text-transform: uppercase;
      color: var(--muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .panel-body {
      padding: 10px 12px;
    }

    /* ---- transcript panel ---- */
    .transcript-col {
      grid-row: 1 / 3;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .transcript-search {
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
    }
    .transcript-search input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 5px 8px;
      font: inherit;
    }
    .transcript-list {
      overflow-y: auto;
      flex: 1;
      max-height: calc(100vh - 200px);
    }
    .seg {
      padding: 6px 12px;
      border-bottom: 1px solid #f0f0f0;
      cursor: pointer;
      transition: background 0.1s;
    }
    .seg:hover { background: var(--primary-soft); }
    .seg.active {
      background: var(--active-seg);
      border-left: 3px solid var(--active-seg-border);
    }
    .seg.hidden { display: none; }
    .seg-meta {
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 2px;
    }
    .seg-speaker { font-weight: bold; color: var(--primary-strong); }
    .seg-text { line-height: 1.4; }

    /* ---- right column ---- */
    .right-col {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* ---- media player ---- */
    .player-wrap audio, .player-wrap video {
      width: 100%;
      max-height: 200px;
    }
    .media-selector {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .media-selector button { font-size: 12px; padding: 3px 8px; }
    .media-selector button.active { background: var(--primary-soft); border-color: var(--primary); }

    /* ---- artifacts panel ---- */
    .artifact-list { list-style: none; margin: 0; padding: 0; }
    .artifact-list li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 0;
      border-bottom: 1px solid #f0f0f0;
      font-size: 13px;
    }
    .artifact-list li:last-child { border-bottom: none; }
    .artifact-name { font-family: monospace; }
    .artifact-size { color: var(--muted); font-size: 11px; margin-left: 6px; }

    /* ---- artifact viewer ---- */
    .artifact-content {
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 10px;
      font-family: monospace;
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 300px;
      overflow-y: auto;
      margin-top: 8px;
    }

    /* ---- jobs panel ---- */
    .jobs-grid {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 4px 12px;
      font-size: 13px;
    }
    .jobs-label { color: var(--muted); }

    /* ---- Q&A placeholder ---- */
    .qa-placeholder {
      color: var(--muted);
      text-align: center;
      padding: 20px;
      font-size: 13px;
    }

    /* ---- auth overlay ---- */
    #auth-overlay {
      display: none;
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.5);
      z-index: 100;
      align-items: center;
      justify-content: center;
    }
    #auth-overlay.visible { display: flex; }
    .auth-box {
      background: var(--surface);
      border-radius: 8px;
      padding: 32px;
      text-align: center;
      max-width: 360px;
    }
    .auth-box h2 { margin: 0 0 12px; }
    .auth-box p { color: var(--muted); margin: 0 0 16px; }

    /* ---- empty/error states ---- */
    .empty { color: var(--muted); padding: 16px; text-align: center; font-size: 13px; }
    .err-msg { color: var(--danger); font-size: 12px; padding: 4px 0; }
  </style>
</head>
<body>

<div id="auth-overlay">
  <div class="auth-box">
    <h2>Login required</h2>
    <p>You must be logged in to view this meeting.</p>
    <a href="/"><button class="primary">Go to login</button></a>
  </div>
</div>

<div class="header">
  <a class="back" href="/" title="Back to meetings list">&#8592;</a>
  <div class="title" id="hdr-title">Loading&hellip;</div>
  <div class="meta" id="hdr-date"></div>
  <span class="badge" id="hdr-status"></span>
  <button onclick="reloadAll()" title="Refresh">&#8635; Refresh</button>
</div>

<div class="workspace">

  <!-- Left: transcript -->
  <div class="panel transcript-col">
    <div class="panel-header">
      Transcript
      <span id="seg-count" style="font-size:11px;font-weight:normal"></span>
    </div>
    <div class="transcript-search">
      <input id="seg-filter" type="text" placeholder="Filter transcript&hellip;"
             oninput="filterSegments(this.value)" />
    </div>
    <div class="transcript-list" id="transcript-list">
      <div class="empty">Loading transcript&hellip;</div>
    </div>
  </div>

  <!-- Right column -->
  <div class="right-col">

    <!-- Media player -->
    <div class="panel">
      <div class="panel-header">Media</div>
      <div class="panel-body" id="media-panel">
        <div class="empty">Loading media&hellip;</div>
      </div>
    </div>

    <!-- Artifacts -->
    <div class="panel">
      <div class="panel-header">
        Artifacts
        <button id="close-artifact-btn" onclick="closeArtifact()" style="display:none;font-size:11px;padding:2px 8px">Close</button>
      </div>
      <div class="panel-body" id="artifacts-panel">
        <div class="empty">Loading artifacts&hellip;</div>
      </div>
    </div>

    <!-- Jobs / status -->
    <div class="panel">
      <div class="panel-header">Processing Status</div>
      <div class="panel-body" id="jobs-panel">
        <div class="empty">Loading&hellip;</div>
      </div>
    </div>

    <!-- Q&A placeholder -->
    <div class="panel">
      <div class="panel-header">Q&amp;A</div>
      <div class="panel-body">
        <div class="qa-placeholder">
          Meeting-scoped Q&amp;A is coming soon.<br />
          Use the <a href="/">main chat</a> for project-level questions.
        </div>
      </div>
    </div>

  </div><!-- right-col -->

</div><!-- workspace -->

<script>
"use strict";

const MEETING_ID = "__MEETING_ID__";

// ---- state ----
let _player = null;
let _segments = [];

// ---- auth ----
function show401() {
  document.getElementById("auth-overlay").classList.add("visible");
}

async function apiFetch(url, opts) {
  const resp = await fetch(url, opts);
  if (resp.status === 401) { show401(); return null; }
  return resp;
}

// ---- formatting ----
function fmtSec(s) {
  if (s == null || isNaN(s)) return "--:--";
  const t = Math.round(s);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}

function fmtBytes(b) {
  if (b == null) return "";
  if (b < 1024) return b + " B";
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
  return (b / 1024 / 1024).toFixed(1) + " MB";
}

function statusBadgeClass(s) {
  if (!s) return "";
  const ok = ["indexed", "summarized", "done", "complete", "finished"];
  const warn = ["processing", "transcribing", "analyzing", "running", "new", "pending"];
  const err = ["error", "failed"];
  if (ok.some(v => s.includes(v))) return "ok";
  if (err.some(v => s.includes(v))) return "err";
  if (warn.some(v => s.includes(v))) return "warn";
  return "";
}

// ---- meeting header ----
async function loadMeeting() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}`);
  if (!resp) return;
  if (!resp.ok) {
    document.getElementById("hdr-title").textContent = "Meeting not found";
    return;
  }
  const d = await resp.json();
  document.getElementById("hdr-title").textContent = d.title || MEETING_ID;
  document.getElementById("hdr-date").textContent = d.date || "";
  const badge = document.getElementById("hdr-status");
  badge.textContent = d.processing_status || "";
  badge.className = "badge " + statusBadgeClass(d.processing_status || "");
  document.title = (d.title || MEETING_ID) + " — Workspace";
}

// ---- media player ----
async function loadMedia() {
  const panel = document.getElementById("media-panel");
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/media`);
  if (!resp) { panel.innerHTML = ""; return; }
  if (!resp.ok) { panel.innerHTML = `<div class="empty">No media</div>`; return; }
  const data = await resp.json();
  const items = data.media || [];
  if (items.length === 0) {
    panel.innerHTML = `<div class="empty">No media files found</div>`;
    return;
  }

  const isVideo = items[0].media_type.startsWith("video/");
  const tag = isVideo ? "video" : "audio";
  const src = `/meetings/${encodeURIComponent(MEETING_ID)}/media/${items[0].media_id}`;

  let selectorHtml = "";
  if (items.length > 1) {
    selectorHtml = `<div class="media-selector" id="media-sel">` +
      items.map((m, i) =>
        `<button class="${i===0?"active":""}" data-media-id="${esc(m.media_id)}" onclick="switchMedia('${esc(m.media_id)}')">`
        + `${esc(m.filename)} (${fmtBytes(m.size_bytes)})</button>`
      ).join("") + `</div>`;
  }

  panel.innerHTML = selectorHtml +
    `<div class="player-wrap">
      <${tag} id="media-player" controls preload="metadata"
        src="${src}">
        Your browser does not support ${tag} playback.
      </${tag}>
    </div>` +
    (items[0].duration_sec ? `<div style="font-size:11px;color:var(--muted);margin-top:4px">Duration: ${fmtSec(items[0].duration_sec)}</div>` : "");

  _player = document.getElementById("media-player");
  _player.addEventListener("timeupdate", onTimeUpdate);
}

function switchMedia(mediaId) {
  if (!_player) return;
  const src = `/meetings/${encodeURIComponent(MEETING_ID)}/media/${encodeURIComponent(mediaId)}`;
  const t = _player.currentTime;
  _player.src = src;
  _player.load();
  _player.currentTime = t;
  document.querySelectorAll("#media-sel button").forEach((b) => {
    b.classList.toggle("active", b.dataset.mediaId === String(mediaId));
  });
}

// ---- transcript ----
async function loadTranscript() {
  const list = document.getElementById("transcript-list");
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/transcript/segments`);
  if (!resp) { list.innerHTML = ""; return; }
  if (!resp.ok) {
    list.innerHTML = `<div class="empty">Transcript not available</div>`;
    return;
  }
  const data = await resp.json();
  _segments = data.segments || [];
  document.getElementById("seg-count").textContent = `${_segments.length} segments`;
  if (_segments.length === 0) {
    list.innerHTML = `<div class="empty">No transcript segments available</div>`;
    return;
  }
  list.innerHTML = _segments.map((seg, i) =>
    `<div class="seg" id="seg-${i}" onclick="seekTo(${seg.start_sec})">
      <div class="seg-meta">
        <span class="seg-time">${fmtSec(seg.start_sec)}</span>
        ${seg.speaker ? ` &mdash; <span class="seg-speaker">${esc(seg.speaker)}</span>` : ""}
      </div>
      <div class="seg-text">${esc(seg.text)}</div>
    </div>`
  ).join("");
}

function seekTo(sec) {
  if (_player && sec != null && !isNaN(sec)) {
    _player.currentTime = sec;
    _player.play().catch(() => {});
  }
}

function onTimeUpdate() {
  if (!_player || _segments.length === 0) return;
  const t = _player.currentTime;
  let active = -1;
  for (let i = 0; i < _segments.length; i++) {
    const s = _segments[i];
    if (s.start_sec != null && s.end_sec != null && t >= s.start_sec && t < s.end_sec) {
      active = i;
      break;
    }
  }
  document.querySelectorAll(".seg").forEach((el, i) => {
    const wasActive = el.classList.contains("active");
    el.classList.toggle("active", i === active);
    if (i === active && !wasActive) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

function filterSegments(q) {
  const lower = q.toLowerCase();
  document.querySelectorAll(".seg").forEach((el, i) => {
    if (!q) { el.classList.remove("hidden"); return; }
    const text = (_segments[i]?.text || "").toLowerCase();
    const speaker = (_segments[i]?.speaker || "").toLowerCase();
    el.classList.toggle("hidden", !text.includes(lower) && !speaker.includes(lower));
  });
}

// ---- artifacts ----
async function loadArtifacts() {
  const panel = document.getElementById("artifacts-panel");
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts`);
  if (!resp) { panel.innerHTML = ""; return; }
  if (!resp.ok) { panel.innerHTML = `<div class="empty">No artifacts</div>`; return; }
  const data = await resp.json();
  const artifacts = (data.artifacts || []).filter(a => a.exists);
  if (artifacts.length === 0) {
    panel.innerHTML = `<div class="empty">No artifacts generated yet</div>`;
    return;
  }
  panel.innerHTML = `<ul class="artifact-list">` +
    artifacts.map(a =>
      `<li>
        <span>
          <span class="artifact-name">${esc(a.key)}</span>
          <span class="artifact-size">${fmtBytes(a.size_bytes)}</span>
        </span>
        <button onclick="viewArtifact('${esc(a.key)}')" style="font-size:11px;padding:2px 8px">View</button>
      </li>`
    ).join("") +
    `</ul><div id="artifact-viewer"></div>`;
}

async function viewArtifact(key) {
  const viewer = document.getElementById("artifact-viewer");
  if (!viewer) return;
  viewer.innerHTML = `<div class="artifact-content">Loading&hellip;</div>`;
  document.getElementById("close-artifact-btn").style.display = "";
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts/${encodeURIComponent(key)}`);
  if (!resp || !resp.ok) {
    viewer.innerHTML = `<div class="err-msg">Could not load artifact.</div>`;
    return;
  }
  const data = await resp.json();
  const content = data.content || "";
  viewer.innerHTML = `<div class="artifact-content">${esc(String(content))}</div>`;
}

function closeArtifact() {
  const viewer = document.getElementById("artifact-viewer");
  if (viewer) viewer.innerHTML = "";
  document.getElementById("close-artifact-btn").style.display = "none";
}

// ---- jobs / status ----
async function loadJobs() {
  const panel = document.getElementById("jobs-panel");
  const [meetResp, jobResp] = await Promise.all([
    apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}`),
    apiFetch("/jobs/active"),
  ]);
  let status = "—";
  if (meetResp && meetResp.ok) {
    const d = await meetResp.json();
    status = d.processing_status || "—";
  }
  let activeJobHtml = "None";
  if (jobResp && jobResp.ok) {
    const j = await jobResp.json();
    if (j && j.job_id && j.meeting_id === MEETING_ID) {
      activeJobHtml = `${esc(j.stage || "")} — <span class="badge ${j.status === "running" ? "warn" : ""}">${esc(j.status || "")}</span>`;
    }
  }
  panel.innerHTML = `<div class="jobs-grid">
    <span class="jobs-label">Status</span>
    <span><span class="badge ${statusBadgeClass(status)}">${esc(status)}</span></span>
    <span class="jobs-label">Active job</span>
    <span>${activeJobHtml}</span>
  </div>`;
}

// ---- helpers ----
function esc(s) {
  if (!s) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---- init ----
async function reloadAll() {
  await Promise.all([
    loadMeeting(),
    loadMedia(),
    loadTranscript(),
    loadArtifacts(),
    loadJobs(),
  ]);
}

reloadAll();
</script>
</body>
</html>
"""


@router.get("/meetings/{meeting_id}/workspace", response_class=HTMLResponse)
def meeting_workspace(meeting_id: str, request: Request) -> HTMLResponse:  # noqa: ARG001
    """Serve the Meeting Workspace single-page UI.

    Auth is enforced by the API calls the page makes — not at this route — to
    be consistent with the existing SPA at GET /.

    Existence is NOT checked here: doing so would let unauthenticated callers
    distinguish 200 vs 404 and probe which meeting IDs exist.  The JS handles
    404 / 401 from the API gracefully.

    Only the meeting_id *format* is validated to prevent injection into the
    embedded JS literal; meeting_id is additionally serialised with json.dumps
    as belt-and-suspenders.
    """
    if not _safe_meeting_id(meeting_id):
        raise HTTPException(status_code=404, detail=f"Meeting not found: {meeting_id!r}")
    # json.dumps produces a quoted, JSON-safe JS string literal including surrounding quotes.
    safe_js_id = _json.dumps(meeting_id)
    html = _WORKSPACE_HTML.replace('"__MEETING_ID__"', safe_js_id)
    return HTMLResponse(content=html)
