"use strict";

const MEETING_ID = document.body.dataset.meetingId || "";

// ---- state ----
let _player = null;
let _segments = [];
let _speakerRows = [];
// CSRF token is held in this in-memory variable only — never written to the
// DOM or to any persistent browser storage.
let _csrfToken = null;
let _permissions = new Set();
let _stages = [];
let _activeJob = null;
let _pollTimer = null;
let _actionInProgress = false;

// ---- auth ----
function showAuthOverlay(title, detail) {
  document.getElementById("auth-overlay-title").textContent = title || "Login required";
  document.getElementById("auth-overlay-detail").textContent =
    detail || "You must be logged in to view this meeting.";
  document.getElementById("auth-overlay").classList.add("visible");
}

function hideAuthOverlay() {
  document.getElementById("auth-overlay").classList.remove("visible");
}

function show401() {
  const auth = document.getElementById("hdr-auth");
  if (auth) {
    auth.textContent = "Not signed in";
    auth.className = "badge warn";
  }
  showAuthOverlay("Login required", "Your session is missing or expired. Open login and sign in again.");
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
  if (!resp) { panel.replaceChildren(); return; }
  if (!resp.ok) { panel.replaceChildren(_mkEmptyMsg("No media")); return; }
  const data = await resp.json();
  const items = data.media || [];
  if (items.length === 0) {
    panel.replaceChildren(_mkEmptyMsg("No media files found"));
    return;
  }

  const isVideo = items[0].media_type.startsWith("video/");
  const tag = isVideo ? "video" : "audio";
  const src = `/meetings/${encodeURIComponent(MEETING_ID)}/media/${items[0].media_id}`;
  const children = [];
  if (items.length > 1) {
    const selector = _mkEl("div", "media-selector");
    selector.id = "media-sel";
    items.forEach((item, index) => {
      const button = _mkEl("button", `media-switch-btn${index === 0 ? " active" : ""}`);
      button.type = "button";
      button.dataset.mediaId = String(item.media_id || "");
      button.textContent = `${item.filename || "Media"} (${fmtBytes(item.size_bytes)})`;
      button.addEventListener("click", () => switchMedia(button.dataset.mediaId));
      selector.appendChild(button);
    });
    children.push(selector);
  }
  const playerWrap = _mkEl("div", "player-wrap");
  _player = document.createElement(tag);
  _player.id = "media-player";
  _player.controls = true;
  _player.preload = "metadata";
  _player.src = src;
  _player.textContent = `Your browser does not support ${tag} playback.`;
  playerWrap.appendChild(_player);
  children.push(playerWrap);
  if (items[0].duration_sec) {
    const duration = _mkEl("div", "media-duration");
    duration.textContent = `Duration: ${fmtSec(items[0].duration_sec)}`;
    children.push(duration);
  }
  panel.replaceChildren(...children);
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
      if (seg.speaker_role) {
        const role = document.createTextNode(` (${seg.speaker_role})`);
        meta.appendChild(role);
      }
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
    const speakerLabel = (_segments[i]?.speaker_label || "").toLowerCase();
    const speakerRole = (_segments[i]?.speaker_role || "").toLowerCase();
    el.classList.toggle(
      "hidden",
      !text.includes(lower) &&
      !speaker.includes(lower) &&
      !speakerLabel.includes(lower) &&
      !speakerRole.includes(lower)
    );
  });
}

// ---- speaker mapping ----
async function loadSpeakerMapping() {
  const panel = document.getElementById("speaker-map-panel");
  const status = document.getElementById("speaker-map-status");
  if (status) {
    status.textContent = "";
    status.classList.remove("err");
  }
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/speakers`);
  if (!resp) { panel.replaceChildren(); return; }
  if (!resp.ok) {
    panel.replaceChildren(_mkEmptyMsg("Speaker mapping not available"));
    return;
  }
  const data = await resp.json();
  _speakerRows = data.speakers || [];
  if (_speakerRows.length === 0) {
    panel.replaceChildren(_mkEmptyMsg("No speaker labels found yet"));
    return;
  }
  const nodes = _speakerRows.map((sp) => {
    const row = _mkEl("div", "speaker-map-row");
    row.dataset.speakerLabel = sp.speaker_label;

    const label = _mkEl("div", "speaker-map-label");
    label.textContent = sp.speaker_label;

    const name = document.createElement("input");
    name.type = "text";
    name.maxLength = 120;
    name.placeholder = "Name";
    name.value = sp.name || "";
    name.dataset.field = "name";

    const role = document.createElement("input");
    role.type = "text";
    role.maxLength = 120;
    role.placeholder = "Role";
    role.value = sp.role || "";
    role.dataset.field = "role";

    row.append(label, name, role);
    return row;
  });
  panel.replaceChildren(...nodes);
}

async function saveSpeakerMapping() {
  const status = document.getElementById("speaker-map-status");
  if (status) {
    status.textContent = "";
    status.classList.remove("err");
  }
  const csrf = await ensureCsrf();
  if (!csrf) {
    if (status) {
      status.textContent = "Login required";
      status.classList.add("err");
    }
    return;
  }
  const mapping = {};
  document.querySelectorAll(".speaker-map-row").forEach((row) => {
    const label = row.dataset.speakerLabel;
    if (!label) return;
    const nameInput = row.querySelector('input[data-field="name"]');
    const roleInput = row.querySelector('input[data-field="role"]');
    const name = (nameInput?.value || "").trim();
    const role = (roleInput?.value || "").trim();
    if (name || role) mapping[label] = { name, role };
  });
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/speakers/mapping`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({ mapping }),
  });
  if (!resp) return;
  if (!resp.ok) {
    if (status) {
      status.textContent = "Could not save speaker mapping";
      status.classList.add("err");
    }
    return;
  }
  await Promise.all([loadSpeakerMapping(), loadTranscript()]);
  if (status) {
    status.textContent = "Saved";
    status.classList.remove("err");
  }
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
    btn.classList.add("compact-btn");
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
  document.getElementById("close-artifact-btn").hidden = false;
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
  document.getElementById("close-artifact-btn").hidden = true;
}

// ---- jobs / pipeline controls ----

function setJobsError(msg) {
  const box = document.getElementById("jobs-error");
  if (!box) return;
  if (!msg) {
    box.hidden = true;
    box.textContent = "";
  } else {
    box.hidden = false;
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
  if (!resp.ok) {
    _permissions = new Set();
    const auth = document.getElementById("hdr-auth");
    if (auth) {
      auth.textContent = "Auth unavailable";
      auth.className = "badge warn";
    }
    return;
  }
  const d = await resp.json();
  _permissions = new Set(Array.isArray(d.permissions) ? d.permissions : []);
  hideAuthOverlay();
  const auth = document.getElementById("hdr-auth");
  if (auth) {
    const label = d.email || "signed in";
    auth.textContent = `Signed in: ${label}`;
    auth.className = "badge ok";
  }
}

async function ensureCsrf() {
  if (_csrfToken) return _csrfToken;
  const resp = await fetch("/auth/csrf");
  if (resp.status === 401) { show401(); return null; }
  if (resp.status === 403) { return null; }
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

let _readiness = {};      // stage -> readiness entry
let _manifest = null;      // artifacts manifest payload
let _failedStage = null;   // stage with state=ready_for_retry
let _jobRecovery = null;   // durable recovery summary from readiness API

async function loadReadiness() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/pipeline/readiness`);
  _readiness = {};
  _failedStage = null;
  _jobRecovery = null;
  if (!resp || !resp.ok) return;
  const d = await resp.json();
  _jobRecovery = d.job_recovery || null;
  for (const st of (Array.isArray(d.stages) ? d.stages : [])) {
    _readiness[st.stage] = st;
    if (st.state === "ready_for_retry") _failedStage = st.stage;
  }
}

async function loadManifest() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts/manifest`);
  _manifest = null;
  if (!resp || !resp.ok) return;
  _manifest = await resp.json();
}

function manifestEntry(key) {
  if (!_manifest || !Array.isArray(_manifest.artifacts)) return null;
  return _manifest.artifacts.find((e) => e.artifact_key === key) || null;
}

let _trackedJobId = null;  // job_id from the last 202 (stage, retry or pipeline)

function _jobIsActive(j) {
  if (!j || !j.job_id) return false;
  if (j.is_active === true) return true;
  // pipeline aggregates report "running"; stage jobs "starting"/"running"
  return j.status === "running" || j.status === "starting" || j.status === "orphaned";
}

async function loadActiveJob() {
  // Prefer polling the exact job we started: survives pipeline gaps between
  // child stages and never mistakes another meeting's job for ours.
  if (_trackedJobId) {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/jobs/${encodeURIComponent(_trackedJobId)}`
    );
    if (resp && resp.ok) {
      const j = await resp.json();
      if (_jobIsActive(j)) { _activeJob = j; return; }
      _trackedJobId = null;  // finished (completed/failed/cancelled)
      _activeJob = null;
      return;
    }
    _trackedJobId = null;
  }
  const resp = await apiFetch("/jobs/active");
  if (!resp || !resp.ok) { _activeJob = null; return; }
  const j = await resp.json();
  _activeJob = (_jobIsActive(j) && j.meeting_id === MEETING_ID) ? j : null;
  if (_activeJob) _trackedJobId = _activeJob.job_id;
}

async function loadMeetingStatus() {
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}`);
  if (!resp || !resp.ok) return "—";
  const d = await resp.json();
  return d.processing_status || "—";
}

// Render the status + stage controls. Uses DOM APIs / textContent / dataset for
// All dynamic stage labels and job fields are rendered through DOM text APIs.
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
    const label = _activeJob.kind === "pipeline"
      ? "pipeline" + (_activeJob.current_stage ? ` (${_activeJob.current_stage})` : "")
      : (_activeJob.stage || "");
    aVal.textContent = label + " ";
    aVal.appendChild(jBadge);
  } else {
    aVal.textContent = "None";
  }
  grid.append(sLabel, sVal, aLabel, aVal);
  if (_jobRecovery) {
    const rLabel = document.createElement("span");
    rLabel.className = "jobs-label";
    rLabel.textContent = "Recovery";
    const rVal = document.createElement("span");
    const recovery = _jobRecovery.recovery_status || _jobRecovery.status || "recovered";
    rVal.textContent = recovery.replace(/_/g, " ");
    grid.append(rLabel, rVal);
  }
  statusEl.appendChild(grid);

  // Cancel control for the active job
  if (_activeJob) {
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "cancel-btn";
    cancelBtn.textContent = "Cancel active job";
    cancelBtn.classList.add("cancel-btn-spaced");
    const canCancel = _permissions.has("jobs.cancel");
    const cancellable = _activeJob.status === "running" ||
      _activeJob.status === "starting" || _activeJob.status === "orphaned";
    cancelBtn.disabled = !canCancel || !cancellable || _actionInProgress;
    if (!canCancel) cancelBtn.title = "Permission required: jobs.cancel";
    cancelBtn.addEventListener("click", () => cancelActiveJob(_activeJob.job_id));
    statusEl.appendChild(cancelBtn);
  }

  // Last error (public-safe detail from readiness previous_failed)
  const lastErrEl = document.getElementById("jobs-last-error");
  const failedEntry = _failedStage ? _readiness[_failedStage] : null;
  if (failedEntry) {
    lastErrEl.hidden = false;
    lastErrEl.textContent =
      `Last error in stage "${_failedStage}": ${failedEntry.detail || "previous run failed"}`;
  } else {
    lastErrEl.hidden = true;
    lastErrEl.textContent = "";
  }

  renderPipelineActions();

  // Stage list with readiness-gated controls
  const stagesEl = document.getElementById("jobs-stages");
  stagesEl.textContent = "";
  const canStart = _permissions.has("jobs.start");
  const canRetry = _permissions.has("jobs.retry");
  for (const st of _stages) {
    const ready = _readiness[st.stage] || null;
    const row = document.createElement("div");
    row.className = "stage-row";

    const info = document.createElement("div");
    info.className = "stage-info";
    const label = document.createElement("div");
    label.className = "stage-label";
    label.textContent = st.label || st.stage;
    if (ready) {
      const state = document.createElement("span");
      state.className = "stage-state " + ready.state;
      state.textContent = ready.state.replace(/_/g, " ");
      label.appendChild(state);
    }
    const desc = document.createElement("div");
    desc.className = "stage-desc";
    if (ready && ready.state === "blocked") {
      desc.textContent = ready.detail || ready.reason || "blocked";
    } else {
      desc.textContent = st.description || "";
    }
    info.append(label, desc);

    const actions = document.createElement("div");
    actions.className = "stage-actions";
    if (ready && ready.state === "done") {
      // Re-running a finished stage is an explicit force action, never default.
      const forceBtn = document.createElement("button");
      forceBtn.textContent = "Force rerun";
      forceBtn.dataset.stage = st.stage;
      forceBtn.disabled = !canRetry || _activeJob !== null || _actionInProgress;
      forceBtn.title = !canRetry
        ? "Permission required: jobs.retry"
        : "Stage output already exists; this re-runs it from scratch";
      forceBtn.addEventListener("click", () => retryStage(forceBtn.dataset.stage, true));
      actions.appendChild(forceBtn);
    } else if (ready && ready.state === "ready_for_retry") {
      const retryBtn = document.createElement("button");
      retryBtn.className = "primary";
      retryBtn.textContent = "Retry";
      retryBtn.dataset.stage = st.stage;
      retryBtn.disabled = !canRetry || _activeJob !== null || _actionInProgress;
      if (!canRetry) retryBtn.title = "Permission required: jobs.retry";
      retryBtn.addEventListener("click", () => retryStage(retryBtn.dataset.stage, false));
      actions.appendChild(retryBtn);
    } else {
      const startBtn = document.createElement("button");
      startBtn.className = "primary";
      startBtn.textContent = "Start";
      startBtn.dataset.stage = st.stage;
      const blocked = ready ? ready.can_run === false : false;
      startBtn.disabled = !canStart || blocked || _activeJob !== null || _actionInProgress;
      if (!canStart) startBtn.title = "Permission required: jobs.start";
      else if (blocked) startBtn.title = ready.detail || "Stage is blocked";
      else if (_activeJob !== null) startBtn.title = "Another job is already running";
      startBtn.addEventListener("click", () => startStage(startBtn.dataset.stage));
      actions.appendChild(startBtn);
    }

    row.append(info, actions);
    stagesEl.appendChild(row);
  }

  renderResults();
  updateQaAvailability();
}

// Pipeline-level actions: run full, resume, retry failed stage.
function renderPipelineActions() {
  const box = document.getElementById("pipeline-actions");
  box.textContent = "";
  const canStart = _permissions.has("jobs.start");
  const canRetry = _permissions.has("jobs.retry");
  const busy = _activeJob !== null || _actionInProgress;

  const states = Object.values(_readiness);
  const anyDone = states.some((s) => s.state === "done");
  const anyPending = states.some((s) => s.state !== "done");

  const runBtn = document.createElement("button");
  runBtn.className = "primary";
  runBtn.textContent = "Run full pipeline";
  runBtn.disabled = !canStart || busy;
  if (!canStart) runBtn.title = "Permission required: jobs.start";
  runBtn.addEventListener("click", () => startPipeline({ profile: "full" }));
  box.appendChild(runBtn);

  if (anyDone && anyPending) {
    const resumeBtn = document.createElement("button");
    resumeBtn.textContent = "Resume pipeline";
    resumeBtn.disabled = !canStart || busy;
    resumeBtn.title = "Continue: done stages are skipped, execution starts at the first pending stage";
    resumeBtn.addEventListener("click", () => startPipeline({ profile: "full", resume: true }));
    box.appendChild(resumeBtn);
  }

  if (_failedStage) {
    const retryBtn = document.createElement("button");
    retryBtn.textContent = "Retry failed stage";
    retryBtn.dataset.stage = _failedStage;
    retryBtn.disabled = !canRetry || busy;
    if (!canRetry) retryBtn.title = "Permission required: jobs.retry";
    retryBtn.addEventListener("click", () => retryStage(retryBtn.dataset.stage, false));
    box.appendChild(retryBtn);
  }
}

// Quick links to results that already exist (manifest-driven).
function renderResults() {
  const box = document.getElementById("pipeline-results");
  box.textContent = "";
  const targets = [
    { key: "segments", label: "Transcript", panel: "transcript-list" },
    { key: "speaker_transcript", label: "Speaker transcript", panel: "artifacts-panel" },
    { key: "memo", label: "Summary", panel: "artifacts-panel" },
    { key: "protocol", label: "Protocol", panel: "artifacts-panel" },
    { key: "tasks", label: "Tasks", panel: "artifacts-panel" },
  ];
  for (const tgt of targets) {
    const entry = manifestEntry(tgt.key);
    if (!entry || !entry.exists) continue;
    const chip = document.createElement("button");
    chip.className = "result-chip";
    chip.textContent = tgt.label + " ✓";
    chip.dataset.panel = tgt.panel;
    chip.addEventListener("click", () => {
      const panel = document.getElementById(chip.dataset.panel);
      if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    box.appendChild(chip);
  }
}

// Meeting Q&A works only after the meeting is indexed.
function updateQaAvailability() {
  const idx = manifestEntry("index_status");
  const chunks = manifestEntry("chunks");
  const available = Boolean((idx && idx.exists) || (chunks && chunks.exists));
  const hint = document.getElementById("qa-availability");
  const askBtn = document.getElementById("qa-ask-btn");
  const searchBtn = document.getElementById("qa-search-btn");
  if (askBtn) askBtn.disabled = !available;
  if (searchBtn) searchBtn.disabled = !available;
  if (hint) {
    hint.textContent = available
      ? ""
      : "Q&A becomes available after the meeting is chunked and indexed (run the pipeline).";
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
    const started = await safeJobBody(resp);
    if (started && started.job_id) _trackedJobId = started.job_id;
  } finally {
    _actionInProgress = false;
  }
  await refreshJobs();
  startPolling();
}

async function safeJobBody(resp) {
  try { return await resp.json(); } catch (e) { return null; }
}

async function startPipeline(opts) {
  if (_actionInProgress) return;
  setJobsError("");
  const csrf = await ensureCsrf();
  if (!csrf) { setJobsError("Could not obtain CSRF token. Please log in again."); return; }
  _actionInProgress = true;
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/jobs/pipeline`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({
          profile: opts.profile || "full",
          resume: Boolean(opts.resume),
          force: Boolean(opts.force),
        }),
      }
    );
    if (!resp) return;
    if (!resp.ok) { setJobsError(await describeError(resp, "Could not start pipeline.")); return; }
    const started = await safeJobBody(resp);
    if (started && started.job_id) _trackedJobId = started.job_id;
  } finally {
    _actionInProgress = false;
  }
  await refreshJobs();
  startPolling();
}

async function retryStage(stage, force) {
  if (_actionInProgress) return;
  setJobsError("");
  const csrf = await ensureCsrf();
  if (!csrf) { setJobsError("Could not obtain CSRF token. Please log in again."); return; }
  _actionInProgress = true;
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/jobs/${encodeURIComponent(stage)}/retry`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ force: Boolean(force) }),
      }
    );
    if (!resp) return;
    if (!resp.ok) { setJobsError(await describeError(resp, "Could not retry stage.")); return; }
    const started = await safeJobBody(resp);
    if (started && started.job_id) _trackedJobId = started.job_id;
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
  const hadActive = _activeJob !== null;
  const [status] = await Promise.all([
    loadMeetingStatus(),
    loadActiveJob(),
    loadReadiness(),
    loadManifest(),
  ]);
  renderJobs(status);
  // Stop polling once no job is active; refresh result panels after a job
  // finished so new transcript/artifacts appear without a manual reload.
  if (!_activeJob && _pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
  if (hadActive && _activeJob === null) {
    await Promise.all([loadTranscript(), loadArtifacts()]);
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
  const csrf = await ensureCsrf();
  if (!csrf) {
    setText("qa-search-status", "");
    setText("qa-search-error", "Could not obtain CSRF token. Please log in again.");
    return;
  }
  let resp;
  try {
    resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
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
    loadSpeakerMapping(),
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

const _speakerMapSaveBtn = document.getElementById("speaker-map-save-btn");
if (_speakerMapSaveBtn) _speakerMapSaveBtn.addEventListener("click", saveSpeakerMapping);

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
