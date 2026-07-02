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
    .jobs-stages { margin-top: 10px; }
    .stage-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px solid #f0f0f0;
    }
    .stage-row:last-child { border-bottom: none; }
    .stage-info { min-width: 0; }
    .stage-label { font-weight: bold; }
    .stage-desc { font-size: 11px; color: var(--muted); }
    .stage-actions { flex-shrink: 0; }
    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      background: var(--surface);
    }
    button:disabled:hover { background: var(--surface); border-color: var(--line); }
    .cancel-btn { border-color: var(--danger); color: var(--danger); }
    .cancel-btn:hover:not(:disabled) { background: #fdeaed; }

    /* ---- Q&A panel ---- */
    .qa-section { display: flex; flex-direction: column; gap: 6px; }
    .qa-section + .qa-section { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
    .qa-section h4 { margin: 0; font-size: 12px; color: var(--muted); font-weight: 600; }
    .qa-input { width: 100%; box-sizing: border-box; resize: vertical; min-height: 38px;
      font: inherit; padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px; }
    .qa-row { display: flex; gap: 6px; }
    .qa-status { font-size: 12px; color: var(--muted); }
    .qa-mode { font-size: 11px; color: var(--muted); font-style: italic; }
    .qa-error { font-size: 12px; color: var(--danger); }
    .qa-answer { font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
    .qa-refusal { font-size: 13px; color: var(--muted); font-style: italic; }
    .qa-citation, .qa-result {
      border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; margin-top: 6px;
      cursor: pointer; font-size: 12px; background: var(--surface);
    }
    .qa-citation:hover, .qa-result:hover { border-color: var(--accent); }
    .qa-cite-meta, .qa-result-meta { color: var(--muted); font-size: 11px; margin-bottom: 2px; }

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
  <button id="hdr-refresh-btn" title="Refresh">&#8635; Refresh</button>
</div>

<div class="workspace">

  <!-- Left: transcript -->
  <div class="panel transcript-col">
    <div class="panel-header">
      Transcript
      <span id="seg-count" style="font-size:11px;font-weight:normal"></span>
    </div>
    <div class="transcript-search">
      <input id="seg-filter" type="text" placeholder="Filter transcript&hellip;" />
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
        <button id="close-artifact-btn" style="display:none;font-size:11px;padding:2px 8px">Close</button>
      </div>
      <div class="panel-body" id="artifacts-panel">
        <div class="empty">Loading artifacts&hellip;</div>
      </div>
    </div>

    <!-- Pipeline controls / status -->
    <div class="panel">
      <div class="panel-header">
        Pipeline
        <button id="jobs-refresh-btn" style="font-size:11px;padding:2px 8px">&#8635; Refresh</button>
      </div>
      <div class="panel-body">
        <div id="jobs-status" class="jobs-status">
          <div class="empty">Loading&hellip;</div>
        </div>
        <div id="jobs-error" class="err-msg" style="display:none"></div>
        <div id="jobs-stages" class="jobs-stages"></div>
      </div>
    </div>

    <!-- Q&A -->
    <div class="panel">
      <div class="panel-header">Q&amp;A</div>
      <div class="panel-body">
        <div class="qa-section">
          <h4>Ask about this meeting</h4>
          <textarea id="qa-question" class="qa-input"
                    placeholder="Ask a question about this meeting&hellip;"></textarea>
          <div class="qa-row">
            <button id="qa-ask-btn">Ask</button>
          </div>
          <div id="qa-chat-status" class="qa-status"></div>
          <div id="qa-chat-mode" class="qa-mode"></div>
          <div id="qa-chat-error" class="qa-error"></div>
          <div id="qa-answer" class="qa-answer"></div>
          <div id="qa-refusal" class="qa-refusal"></div>
          <div id="qa-citations"></div>
        </div>

        <div class="qa-section">
          <h4>Search in meeting</h4>
          <div class="qa-row">
            <input id="qa-search-input" class="qa-input" type="text"
                   placeholder="Search transcript &amp; artifacts&hellip;" />
            <button id="qa-search-btn">Search</button>
          </div>
          <div id="qa-search-status" class="qa-status"></div>
          <div id="qa-search-mode" class="qa-mode"></div>
          <div id="qa-search-error" class="qa-error"></div>
          <div id="qa-search-results"></div>
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
// CSRF token is held in this in-memory variable only — never written to the
// DOM or to any persistent browser storage.
let _csrfToken = null;
let _permissions = new Set();
let _stages = [];
let _activeJob = null;
let _pollTimer = null;
let _actionInProgress = false;

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
        `<button class="media-switch-btn ${i===0?"active":""}" data-media-id="${esc(m.media_id)}">`
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

  panel.querySelectorAll(".media-switch-btn").forEach(btn => {
    btn.addEventListener("click", () => switchMedia(btn.dataset.mediaId));
  });

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
  document.querySelectorAll(".media-switch-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.mediaId === String(mediaId));
  });
}

// ---- transcript ----
function _mkEl(tag, className) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  return el;
}

function _mkEmptyMsg(msg) {
  const div = _mkEl("div", "empty");
  div.textContent = msg;
  return div;
}

async function loadTranscript() {
  const list = document.getElementById("transcript-list");
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/transcript/segments`);
  if (!resp) { list.replaceChildren(); return; }
  if (!resp.ok) {
    list.replaceChildren(_mkEmptyMsg("Transcript not available"));
    return;
  }
  const data = await resp.json();
  _segments = data.segments || [];
  document.getElementById("seg-count").textContent = `${_segments.length} segments`;
  if (_segments.length === 0) {
    list.replaceChildren(_mkEmptyMsg("No transcript segments available"));
    return;
  }
  const nodes = _segments.map((seg, i) => {
    const div = _mkEl("div", "seg");
    div.id = `seg-${i}`;
    if (seg.start_sec != null) div.dataset.startSec = seg.start_sec;

    const meta = _mkEl("div", "seg-meta");
    const time = _mkEl("span", "seg-time");
    time.textContent = fmtSec(seg.start_sec);
    meta.appendChild(time);
    if (seg.speaker) {
      const sep = document.createTextNode(" — ");
      meta.appendChild(sep);
      const spk = _mkEl("span", "seg-speaker");
      spk.textContent = seg.speaker;
      meta.appendChild(spk);
    }

    const txt = _mkEl("div", "seg-text");
    txt.textContent = seg.text;

    div.appendChild(meta);
    div.appendChild(txt);
    div.addEventListener("click", () => {
      if (seg.start_sec != null) seekTo(seg.start_sec);
    });
    return div;
  });
  list.replaceChildren(...nodes);
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
  if (!resp) { panel.replaceChildren(); return; }
  if (!resp.ok) { panel.replaceChildren(_mkEmptyMsg("No artifacts")); return; }
  const data = await resp.json();
  const artifacts = (data.artifacts || []).filter(a => a.exists);
  if (artifacts.length === 0) {
    panel.replaceChildren(_mkEmptyMsg("No artifacts generated yet"));
    return;
  }
  const ul = _mkEl("ul", "artifact-list");
  artifacts.forEach(a => {
    const li = document.createElement("li");

    const nameWrap = document.createElement("span");
    const nameSpan = _mkEl("span", "artifact-name");
    nameSpan.textContent = a.key;
    const sizeSpan = _mkEl("span", "artifact-size");
    sizeSpan.textContent = fmtBytes(a.size_bytes);
    nameWrap.appendChild(nameSpan);
    nameWrap.appendChild(sizeSpan);

    const btn = document.createElement("button");
    btn.className = "view-artifact-btn";
    btn.dataset.artifactKey = a.key;
    btn.style.cssText = "font-size:11px;padding:2px 8px";
    btn.textContent = "View";
    btn.addEventListener("click", () => viewArtifact(btn.dataset.artifactKey));

    li.appendChild(nameWrap);
    li.appendChild(btn);
    ul.appendChild(li);
  });
  const viewerDiv = document.createElement("div");
  viewerDiv.id = "artifact-viewer";
  panel.replaceChildren(ul, viewerDiv);
}

async function viewArtifact(key) {
  const viewer = document.getElementById("artifact-viewer");
  if (!viewer) return;
  const loading = _mkEl("div", "artifact-content");
  loading.textContent = "Loading…";
  viewer.replaceChildren(loading);
  document.getElementById("close-artifact-btn").style.display = "";
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts/${encodeURIComponent(key)}`);
  if (!resp || !resp.ok) {
    const errDiv = _mkEl("div", "err-msg");
    errDiv.textContent = "Could not load artifact.";
    viewer.replaceChildren(errDiv);
    return;
  }
  const data = await resp.json();
  const contentDiv = _mkEl("div", "artifact-content");
  contentDiv.textContent = String(data.content || "");
  viewer.replaceChildren(contentDiv);
}

function closeArtifact() {
  const viewer = document.getElementById("artifact-viewer");
  if (viewer) viewer.replaceChildren();
  document.getElementById("close-artifact-btn").style.display = "none";
}

// ---- jobs / pipeline controls ----

function setJobsError(msg) {
  const box = document.getElementById("jobs-error");
  if (!box) return;
  if (!msg) {
    box.style.display = "none";
    box.textContent = "";
  } else {
    box.style.display = "";
    box.textContent = msg;  // textContent: never interprets HTML
  }
}

// Map an API error response to a controlled, user-facing message. Never
// renders raw backend HTML or stack traces.
async function describeError(resp, fallback) {
  if (resp.status === 403) return "Permission required for this action.";
  if (resp.status === 409) {
    const d = await safeDetail(resp);
    return d || "Another job is already running.";
  }
  if (resp.status === 404) return "Meeting or job not found.";
  if (resp.status === 422) {
    const d = await safeDetail(resp);
    return d || "Request was rejected (invalid stage or preconditions).";
  }
  return fallback || "Request failed.";
}

async function safeDetail(resp) {
  try {
    const d = await resp.json();
    if (typeof d.detail === "string") return d.detail;
    if (d.detail && typeof d.detail === "object") return null;
  } catch (e) { /* not JSON */ }
  return null;
}

async function loadPermissions() {
  const resp = await fetch("/auth/me");
  if (resp.status === 401) { show401(); _permissions = new Set(); return; }
  if (!resp.ok) { _permissions = new Set(); return; }
  const d = await resp.json();
  _permissions = new Set(Array.isArray(d.permissions) ? d.permissions : []);
}

async function ensureCsrf() {
  if (_csrfToken) return _csrfToken;
  const resp = await fetch("/auth/csrf");
  if (resp.status === 401) { show401(); return null; }
  if (!resp.ok) return null;
  const d = await resp.json();
  _csrfToken = d.csrf_token || null;
  return _csrfToken;
}

async function loadStages() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/jobs/stages`);
  if (!resp || !resp.ok) { _stages = []; return; }
  const d = await resp.json();
  _stages = Array.isArray(d.stages) ? d.stages : [];
}

async function loadActiveJob() {
  const resp = await apiFetch("/jobs/active");
  if (!resp || !resp.ok) { _activeJob = null; return; }
  const j = await resp.json();
  _activeJob = (j && j.job_id && j.meeting_id === MEETING_ID) ? j : null;
}

async function loadMeetingStatus() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}`);
  if (!resp || !resp.ok) return "—";
  const d = await resp.json();
  return d.processing_status || "—";
}

// Render the status + stage controls. Uses DOM APIs / textContent / dataset for
// all dynamic values — no innerHTML interpolation of stage labels or job fields.
function renderJobs(status) {
  const statusEl = document.getElementById("jobs-status");
  statusEl.textContent = "";
  const grid = document.createElement("div");
  grid.className = "jobs-grid";

  const sLabel = document.createElement("span");
  sLabel.className = "jobs-label";
  sLabel.textContent = "Status";
  const sVal = document.createElement("span");
  const sBadge = document.createElement("span");
  sBadge.className = "badge " + statusBadgeClass(status);
  sBadge.textContent = status;
  sVal.appendChild(sBadge);

  const aLabel = document.createElement("span");
  aLabel.className = "jobs-label";
  aLabel.textContent = "Active job";
  const aVal = document.createElement("span");
  if (_activeJob) {
    const jBadge = document.createElement("span");
    jBadge.className = "badge " + (_activeJob.status === "running" ? "warn" : "");
    jBadge.textContent = _activeJob.status || "";
    aVal.textContent = (_activeJob.stage || "") + " ";
    aVal.appendChild(jBadge);
  } else {
    aVal.textContent = "None";
  }
  grid.append(sLabel, sVal, aLabel, aVal);
  statusEl.appendChild(grid);

  // Cancel control for the active job
  if (_activeJob) {
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "cancel-btn";
    cancelBtn.textContent = "Cancel active job";
    cancelBtn.style.marginTop = "8px";
    const canCancel = _permissions.has("jobs.cancel");
    const cancellable = _activeJob.status === "running" || _activeJob.status === "starting";
    cancelBtn.disabled = !canCancel || !cancellable || _actionInProgress;
    if (!canCancel) cancelBtn.title = "Permission required: jobs.cancel";
    cancelBtn.addEventListener("click", () => cancelActiveJob(_activeJob.job_id));
    statusEl.appendChild(cancelBtn);
  }

  // Stage list with Start buttons
  const stagesEl = document.getElementById("jobs-stages");
  stagesEl.textContent = "";
  const canStart = _permissions.has("jobs.start");
  for (const st of _stages) {
    const row = document.createElement("div");
    row.className = "stage-row";

    const info = document.createElement("div");
    info.className = "stage-info";
    const label = document.createElement("div");
    label.className = "stage-label";
    label.textContent = st.label || st.stage;
    const desc = document.createElement("div");
    desc.className = "stage-desc";
    desc.textContent = st.description || "";
    info.append(label, desc);

    const actions = document.createElement("div");
    actions.className = "stage-actions";
    const startBtn = document.createElement("button");
    startBtn.className = "primary";
    startBtn.textContent = "Start";
    startBtn.dataset.stage = st.stage;
    startBtn.disabled = !canStart || _activeJob !== null || _actionInProgress;
    if (!canStart) startBtn.title = "Permission required: jobs.start";
    else if (_activeJob !== null) startBtn.title = "Another job is already running";
    startBtn.addEventListener("click", () => startStage(startBtn.dataset.stage));
    actions.appendChild(startBtn);

    row.append(info, actions);
    stagesEl.appendChild(row);
  }
}

async function startStage(stage) {
  if (_actionInProgress) return;
  setJobsError("");
  const csrf = await ensureCsrf();
  if (!csrf) { setJobsError("Could not obtain CSRF token. Please log in again."); return; }
  _actionInProgress = true;
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/jobs/${encodeURIComponent(stage)}`,
      { method: "POST", headers: { "X-CSRF-Token": csrf } }
    );
    if (!resp) return;  // 401 handled
    if (!resp.ok) { setJobsError(await describeError(resp, "Could not start job.")); return; }
  } finally {
    _actionInProgress = false;
  }
  await refreshJobs();
  startPolling();
}

async function cancelActiveJob(jobId) {
  if (_actionInProgress) return;
  setJobsError("");
  const csrf = await ensureCsrf();
  if (!csrf) { setJobsError("Could not obtain CSRF token. Please log in again."); return; }
  _actionInProgress = true;
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: "POST", headers: { "X-CSRF-Token": csrf } }
    );
    if (!resp) return;
    if (!resp.ok) { setJobsError(await describeError(resp, "Could not cancel job.")); return; }
  } finally {
    _actionInProgress = false;
  }
  await refreshJobs();
}

async function refreshJobs() {
  const [status] = await Promise.all([
    loadMeetingStatus(),
    loadActiveJob(),
  ]);
  renderJobs(status);
  // Stop polling once no job is active.
  if (!_activeJob && _pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

function startPolling() {
  if (_pollTimer) return;
  _pollTimer = setInterval(refreshJobs, 3000);
}

async function loadJobs() {
  await Promise.all([loadPermissions(), loadStages()]);
  await refreshJobs();
  if (_activeJob) startPolling();
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

// ---- Q&A: meeting-scoped search ----
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || "";
}

function qaCiteLine(src) {
  const parts = [];
  if (src && src.citation_label) {
    parts.push(src.citation_label);  // "[00:12:34, Speaker]" from Q&A v2
  } else {
    if (src && src.start_sec != null) parts.push(fmtSec(src.start_sec));
    if (src && src.speaker) parts.push(src.speaker);
  }
  if (src && src.artifact) parts.push(src.artifact);
  return parts.join(" · ");
}

function qaModeLabel(mode) {
  if (mode === "vector") return "retrieval: semantic (vector)";
  if (mode === "lexical") return "retrieval: lexical";
  return "";
}

async function meetingSearch() {
  const input = document.getElementById("qa-search-input");
  const query = (input.value || "").trim();
  setText("qa-search-error", "");
  setText("qa-search-status", "");
  setText("qa-search-mode", "");
  const container = document.getElementById("qa-search-results");
  container.replaceChildren();
  if (!query) return;
  setText("qa-search-status", "Searching…");
  let resp;
  try {
    resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, top_k: 5 }),
    });
  } catch (e) {
    setText("qa-search-status", "");
    setText("qa-search-error", "Search request failed. Please try again.");
    return;
  }
  if (!resp) return;  // 401 handled by overlay
  if (!resp.ok) {
    setText("qa-search-status", "");
    setText("qa-search-error", await describeError(resp, "Search failed."));
    return;
  }
  const data = await resp.json();
  const results = Array.isArray(data.results) ? data.results : [];
  setText("qa-search-status", results.length ? "" : "No matches in this meeting.");
  setText("qa-search-mode", qaModeLabel(data.retrieval_mode));
  for (const r of results) {
    const src = r.source || {};
    const card = document.createElement("div");
    card.className = "qa-result";
    const meta = document.createElement("div");
    meta.className = "qa-result-meta";
    meta.textContent = qaCiteLine(src) || "meeting";
    const body = document.createElement("div");
    body.textContent = r.text || "";
    card.appendChild(meta);
    card.appendChild(body);
    if (src.start_sec != null) {
      card.dataset.startSec = String(src.start_sec);
      card.addEventListener("click", () => seekTo(Number(card.dataset.startSec)));
    }
    container.appendChild(card);
  }
}

async function askQuestion() {
  if (_actionInProgress) return;
  const textarea = document.getElementById("qa-question");
  const query = (textarea.value || "").trim();
  setText("qa-chat-error", "");
  setText("qa-chat-mode", "");
  setText("qa-answer", "");
  setText("qa-refusal", "");
  document.getElementById("qa-citations").replaceChildren();
  if (!query) return;
  setText("qa-chat-status", "Thinking…");
  const csrf = await ensureCsrf();
  if (!csrf) { setText("qa-chat-status", ""); setText("qa-chat-error", "Could not obtain CSRF token. Please log in again."); return; }
  _actionInProgress = true;
  let resp;
  try {
    resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ query: query, top_k: 5 }),
    });
  } catch (e) {
    setText("qa-chat-status", "");
    setText("qa-chat-error", "Chat request failed. Please try again.");
    return;
  } finally {
    _actionInProgress = false;
  }
  setText("qa-chat-status", "");
  if (!resp) return;  // 401 handled
  if (!resp.ok) { setText("qa-chat-error", await describeError(resp, "Could not get an answer.")); return; }
  const data = await resp.json();
  setText("qa-chat-mode", qaModeLabel(data.retrieval_mode));
  if (data.answer) {
    setText("qa-answer", data.answer);
  } else if (data.refusal) {
    setText("qa-refusal", data.refusal);
  } else {
    setText("qa-refusal", "No answer was produced for this meeting.");
  }
  const citations = Array.isArray(data.citations) ? data.citations : [];
  const container = document.getElementById("qa-citations");
  for (const c of citations) {
    const card = document.createElement("div");
    card.className = "qa-citation";
    const meta = document.createElement("div");
    meta.className = "qa-cite-meta";
    meta.textContent = qaCiteLine(c) || "source";
    const body = document.createElement("div");
    body.textContent = c.excerpt || "";
    card.appendChild(meta);
    card.appendChild(body);
    if (c.start_sec != null) {
      card.dataset.startSec = String(c.start_sec);
      card.addEventListener("click", () => seekTo(Number(card.dataset.startSec)));
    }
    container.appendChild(card);
  }
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

const _hdrRefreshBtn = document.getElementById("hdr-refresh-btn");
if (_hdrRefreshBtn) _hdrRefreshBtn.addEventListener("click", reloadAll);

const _segFilter = document.getElementById("seg-filter");
if (_segFilter) _segFilter.addEventListener("input", (e) => filterSegments(e.target.value));

const _closeArtifactBtn = document.getElementById("close-artifact-btn");
if (_closeArtifactBtn) _closeArtifactBtn.addEventListener("click", closeArtifact);

const _jobsRefreshBtn = document.getElementById("jobs-refresh-btn");
if (_jobsRefreshBtn) {
  _jobsRefreshBtn.addEventListener("click", () => { setJobsError(""); refreshJobs(); });
}

const _qaAskBtn = document.getElementById("qa-ask-btn");
if (_qaAskBtn) _qaAskBtn.addEventListener("click", askQuestion);
const _qaSearchBtn = document.getElementById("qa-search-btn");
if (_qaSearchBtn) _qaSearchBtn.addEventListener("click", meetingSearch);
const _qaSearchInput = document.getElementById("qa-search-input");
if (_qaSearchInput) {
  _qaSearchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") meetingSearch(); });
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
