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
let _meetingDetail = null;
let _activeWorkspaceTab = "transcript";

const LIVE_SOURCES = ["MIC", "SYS"];
const LIVE_FINAL_ROWS_MAX = 250;
const LIVE_CONVERSATION_ROWS_MAX = 500;
const LIVE_POLL_INTERVAL_MS = 750;
const _liveTracks = {
  MIC: {
    preflight: null, session: null, cursor: 0, partial: "", finals: [],
    devicesRevision: 0, renderedDevicesRevision: -1,
    finalsRevision: 0,
  },
  SYS: {
    preflight: null, session: null, cursor: 0, partial: "", finals: [],
    devicesRevision: 0, renderedDevicesRevision: -1,
    finalsRevision: 0,
  },
};
let _liveGroupBusy = false;
let _livePollTimer = null;
let _liveClockTimer = null;
let _livePollInFlight = false;
const _liveTimeline = {
  segments: [],
  timelineStartedAt: null,
  warnings: [],
  revision: 0,
  renderedKey: null,
};

function setWorkspaceTab(tabName) {
  const target = document.querySelector(`[data-workspace-panel="${tabName}"]`)
    ? tabName
    : "transcript";
  _activeWorkspaceTab = target;
  document.querySelectorAll("[data-workspace-tab]").forEach((button) => {
    const active = button.dataset.workspaceTab === target;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  document.querySelectorAll("[data-workspace-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.workspacePanel !== target;
    panel.classList.toggle("active", panel.dataset.workspacePanel === target);
  });
  const tabButton = document.querySelector(`[data-workspace-tab="${target}"]`);
  if (tabButton) tabButton.scrollIntoView({ block: "nearest", inline: "nearest" });
}

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
    auth.textContent = "Вход не выполнен";
    auth.className = "badge warn";
  }
  showAuthOverlay("Требуется вход", "Сессия отсутствует или завершена. Откройте MeetingAgent и войдите снова.");
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
    document.getElementById("hdr-title").textContent = "Встреча не найдена";
    return;
  }
  const d = await resp.json();
  _meetingDetail = d;
  document.getElementById("hdr-title").textContent = d.title || MEETING_ID;
  const dateParts = [d.date, d.start_time, d.duration_minutes ? `${d.duration_minutes} мин` : ""]
    .filter(Boolean);
  document.getElementById("hdr-date").textContent = dateParts.join(" · ");
  const badge = document.getElementById("hdr-status");
  badge.textContent = d.processing_status || "";
  badge.className = "badge " + statusBadgeClass(d.processing_status || "");
  document.getElementById("overview-title").textContent = d.title || MEETING_ID;
  document.getElementById("overview-date").textContent = dateParts.join(" · ") || "—";
  document.getElementById("overview-status").textContent = d.processing_status || "—";
  const participants = Array.isArray(d.participants) ? d.participants : [];
  document.getElementById("overview-participants").textContent = participants.length
    ? participants.join(", ")
    : "Не указаны";
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
    list.replaceChildren(_mkEmptyMsg("Транскрипт пока недоступен"));
    return;
  }
  const data = await resp.json();
  _segments = data.segments || [];
  document.getElementById("seg-count").textContent = `${_segments.length} сегментов`;
  if (_segments.length === 0) {
    list.replaceChildren(_mkEmptyMsg("Сегменты транскрипта пока не созданы"));
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
  setWorkspaceTab("transcript");
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

// ---- live transcription draft ----

const LIVE_REASON_TEXT = {
  model_missing: "Локальная модель Vosk не установлена или повреждена.",
  model_path_unsupported: "В Windows модель Vosk должна находиться в каталоге без кириллицы.",
  sounddevice_missing: "Компонент захвата микрофона не установлен.",
  mic_input_device_missing: "Микрофон не найден.",
  mic_input_device_not_found: "Выбранный микрофон больше недоступен.",
  mic_capture_format_unsupported: "Микрофон не поддерживает mono 16 кГц.",
  sys_loopback_windows_only: "Захват системного звука доступен только в Windows.",
  sys_loopback_backend_missing: "Компонент Windows loopback не установлен.",
  sys_loopback_discovery_failed: "Не удалось проверить устройства системного звука.",
  sys_loopback_device_missing: "Loopback-устройство системного звука не найдено.",
  sys_loopback_device_not_found: "Выбранное loopback-устройство больше недоступно.",
  sys_loopback_default_missing: "Loopback-устройство по умолчанию не найдено.",
  source_preflight_failed: "Не удалось проверить готовность аудиоисточника.",
  live_session_active: "Для этого источника уже идёт live-сессия.",
  offline_job_active: "Перед live-записью остановите offline-обработку встречи.",
  live_session_capacity: "Достигнут лимит live-захвата. Остановите другой источник.",
  live_artifact_exists: "Черновик уже существует. Подтвердите замену для новой записи.",
  live_session_not_running: "Процесс захвата остановлен. Обновите панель Live.",
  service_stopping: "Сервис live-транскрибации останавливается.",
  meeting_not_found: "Встреча больше недоступна.",
  live_state_unavailable: "Состояние live-сессии временно недоступно.",
  live_session_failed: "Live-транскрибация завершилась ошибкой. Проверьте аудио и модель.",
  live_audio_missing: "Сохранённое live-аудио отсутствует.",
  live_segments_missing: "Сохранённый черновик транскрипта отсутствует.",
  live_report_missing: "Отчёт live-сессии отсутствует.",
  live_audio_not_registered: "Live-аудио не зарегистрировано в карточке встречи.",
  live_draft_index_policy_invalid: "Политика индексации черновика небезопасна; запишите источник заново.",
  refinement_active: "Offline-уточнение уже выполняется.",
  refinement_already_final: "Канонический транскрипт уже существует. Подтвердите замену.",
  refinement_resume_required: "Предыдущее уточнение завершилось ошибкой. Продолжите или замените результат.",
  refinement_preflight_failed: "Проверка offline ASR не пройдена. Проверьте выбранный движок.",
  refinement_interrupted: "Offline-уточнение прервано; его можно продолжить.",
  refinement_report_invalid: "Отчёт уточнения повреждён. Продолжите обработку.",
  refinement_report_missing: "Отчёт уточнения отсутствует. Продолжите обработку.",
};

function liveElement(source, suffix) {
  return document.getElementById(`live-${source.toLowerCase()}-${suffix}`);
}

function liveReasonText(reason) {
  return LIVE_REASON_TEXT[reason] || "Аудиоисточник не готов.";
}

function liveIsActive(session) {
  return Boolean(session && session.is_active === true);
}

function anyLiveActive() {
  return LIVE_SOURCES.some((source) => liveIsActive(_liveTracks[source].session));
}

function setLiveError(source, message) {
  if (message) setLiveGlobalError(`${source}: ${message}`);
}

function setLiveGlobalError(message) {
  const box = document.getElementById("live-global-error");
  if (!box) return;
  box.hidden = !message;
  box.textContent = message || "";
}

function liveElapsedSeconds(session) {
  if (!session || !session.started_at) return 0;
  const started = Date.parse(session.started_at);
  if (!Number.isFinite(started)) return 0;
  const finished = session.is_active ? Date.now() : Date.parse(session.finished_at || "");
  const end = Number.isFinite(finished) ? finished : Date.now();
  return Math.max(0, Math.floor((end - started) / 1000));
}

function fmtElapsed(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = Math.floor(value % 60);
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function updateLiveElapsed() {
  const elapsed = document.getElementById("live-elapsed");
  if (!elapsed) return;
  const values = LIVE_SOURCES.map((source) => liveElapsedSeconds(_liveTracks[source].session));
  elapsed.textContent = fmtElapsed(Math.max(...values, 0));
}

function selectedLiveDevice(source) {
  const select = liveElement(source, "device");
  if (!select || select.value === "") return null;
  const value = Number(select.value);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function renderLiveDeviceOptions(source) {
  const state = _liveTracks[source];
  const select = liveElement(source, "device");
  if (!select) return;
  if (state.renderedDevicesRevision === state.devicesRevision) {
    select.disabled = anyLiveActive() || _liveGroupBusy;
    return;
  }
  const previous = select.value;
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = source === "MIC" ? "System default microphone" : "Default loopback device";
  const options = [defaultOption];
  const devices = state.preflight && Array.isArray(state.preflight.devices)
    ? state.preflight.devices
    : [];
  for (const device of devices) {
    if (!Number.isInteger(device.device_index) || device.device_index < 0) continue;
    const option = document.createElement("option");
    option.value = String(device.device_index);
    option.textContent = device.label || `Audio device ${device.device_index}`;
    options.push(option);
  }
  select.replaceChildren(...options);
  if (previous && options.some((option) => option.value === previous)) select.value = previous;
  state.renderedDevicesRevision = state.devicesRevision;
  select.disabled = anyLiveActive() || _liveGroupBusy;
}

function renderLiveWarnings() {
  const list = document.getElementById("live-warnings");
  if (!list) return;
  const warnings = LIVE_SOURCES.flatMap((source) => {
    const session = _liveTracks[source].session;
    return session && Array.isArray(session.warnings)
      ? session.warnings.map((warning) => `${source}: ${String(warning).replace(/_/g, " ")}`)
      : [];
  });
  const nodes = warnings.map((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    return item;
  });
  list.replaceChildren(...nodes);
  list.hidden = nodes.length === 0;
}

function liveEpoch(value) {
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp / 1000 : null;
}

function liveConversationRows() {
  const activeSources = new Set(
    LIVE_SOURCES.filter((source) => liveIsActive(_liveTracks[source].session))
  );
  const saved = _liveTimeline.segments.filter(
    (segment) => !activeSources.has(segment.source)
  );
  const savedEpoch = saved.length > 0 ? liveEpoch(_liveTimeline.timelineStartedAt) : null;
  const sessionEpochs = LIVE_SOURCES.map((source) => ({
    source,
    epoch: liveEpoch(_liveTracks[source].session && _liveTracks[source].session.started_at),
  })).filter((item) => (
    item.epoch !== null &&
    (liveIsActive(_liveTracks[item.source].session) || _liveTracks[item.source].finals.length > 0)
  ));
  const candidates = sessionEpochs.map((item) => item.epoch);
  if (savedEpoch !== null) candidates.push(savedEpoch);
  const timelineEpoch = candidates.length > 0 ? Math.min(...candidates) : 0;
  const rows = new Map();

  for (const segment of saved) {
    const source = segment.source === "SYS" ? "SYS" : "MIC";
    const key = `${source}:${String(segment.origin_segment_id || segment.segment_id || "")}`;
    const offset = savedEpoch === null ? 0 : Math.max(0, savedEpoch - timelineEpoch);
    rows.set(key, {
      key,
      source,
      speaker: String(segment.speaker || segment.speaker_label || ""),
      start: offset + (Number(segment.start) || 0),
      end: offset + (Number(segment.end) || 0),
      text: String(segment.text || ""),
    });
  }

  for (const source of LIVE_SOURCES) {
    const state = _liveTracks[source];
    const sessionEpoch = liveEpoch(state.session && state.session.started_at);
    const offset = sessionEpoch === null ? 0 : Math.max(0, sessionEpoch - timelineEpoch);
    for (const event of state.finals) {
      const originId = String(event.segmentId || `event-${event.eventId}`);
      const key = `${source}:${originId}`;
      rows.set(key, {
        key,
        source,
        speaker: "",
        start: offset + (Number(event.start) || 0),
        end: offset + (Number(event.end) || 0),
        text: String(event.text || ""),
      });
    }
  }

  return [...rows.values()]
    .filter((row) => row.text.trim())
    .sort((left, right) => (
      left.start - right.start ||
      (left.source === right.source ? 0 : left.source === "MIC" ? -1 : 1) ||
      left.key.localeCompare(right.key) ||
      left.end - right.end
    ))
    .slice(-LIVE_CONVERSATION_ROWS_MAX);
}

function renderLiveConversation() {
  const list = document.getElementById("live-conversation-finals");
  const badge = document.getElementById("live-conversation-badge");
  if (!list || !badge) return;
  const renderKey = JSON.stringify({
    timeline: _liveTimeline.revision,
    tracks: LIVE_SOURCES.map((source) => ({
      revision: _liveTracks[source].finalsRevision,
      status: _liveTracks[source].session && _liveTracks[source].session.status,
      startedAt: _liveTracks[source].session && _liveTracks[source].session.started_at,
    })),
  });
  if (_liveTimeline.renderedKey === renderKey) return;
  const rows = liveConversationRows();
  badge.textContent = rows.length > 0 ? `${rows.length} final lines` : "MIX draft";
  badge.className = `badge${rows.length > 0 ? " ok" : ""}`;
  badge.title = _liveTimeline.warnings.length > 0
    ? _liveTimeline.warnings.map((warning) => String(warning).replace(/_/g, " ")).join("; ")
    : "Derived final MIC and SYS transcript timeline";
  if (rows.length === 0) {
    list.replaceChildren(_mkEmptyMsg("No final conversation lines yet"));
    _liveTimeline.renderedKey = renderKey;
    return;
  }
  const nodes = rows.map((rowData) => {
    const row = _mkEl("div", "live-conversation-row");
    const source = _mkEl("span", "live-conversation-source");
    source.dataset.source = rowData.source;
    source.textContent = rowData.speaker || rowData.source;
    source.title = rowData.speaker
      ? `${rowData.source} · preliminary Diart speaker`
      : rowData.source;
    const content = _mkEl("div", "live-conversation-content");
    const meta = _mkEl("div", "live-conversation-meta");
    meta.textContent = `${fmtSec(rowData.start)}–${fmtSec(rowData.end)} · ${rowData.source}`;
    const text = _mkEl("div", "live-conversation-text");
    text.textContent = rowData.text;
    content.append(meta, text);
    row.append(source, content);
    return row;
  });
  list.replaceChildren(...nodes);
  list.scrollTop = list.scrollHeight;
  _liveTimeline.renderedKey = renderKey;
}

async function loadLiveTimeline() {
  const base = `/meetings/${encodeURIComponent(MEETING_ID)}/live/timeline`;
  try {
    let resp = await apiFetch(`${base}?after=0&limit=${LIVE_CONVERSATION_ROWS_MAX}`);
    if (!resp || !resp.ok) return;
    let body = await resp.json();
    const total = Number(body.total) || 0;
    if (total > LIVE_CONVERSATION_ROWS_MAX) {
      const after = Math.max(0, total - LIVE_CONVERSATION_ROWS_MAX);
      resp = await apiFetch(`${base}?after=${after}&limit=${LIVE_CONVERSATION_ROWS_MAX}`);
      if (!resp || !resp.ok) return;
      body = await resp.json();
    }
    _liveTimeline.segments = Array.isArray(body.segments) ? body.segments : [];
    _liveTimeline.timelineStartedAt = body.timeline_started_at || null;
    _liveTimeline.warnings = Array.isArray(body.warnings) ? body.warnings.slice(0, 50) : [];
    _liveTimeline.revision += 1;
    _liveTimeline.renderedKey = null;
    renderLiveConversation();
  } catch (e) {
    setLiveGlobalError("Не удалось обновить сохранённую ленту разговора.");
  }
}

function renderLiveTrack(source) {
  renderLiveDeviceOptions(source);
  renderLiveCapture();
}

function renderLiveCapture() {
  const badge = document.getElementById("live-capture-badge");
  const status = document.getElementById("live-capture-status");
  const start = document.getElementById("live-start-btn");
  const stop = document.getElementById("live-stop-btn");
  const vad = document.getElementById("live-vad");
  const force = document.getElementById("live-force");
  const partial = document.getElementById("live-partial");
  if (!badge || !status || !start || !stop || !vad || !force || !partial) return;

  const activeSources = LIVE_SOURCES.filter((source) => liveIsActive(_liveTracks[source].session));
  const readySources = LIVE_SOURCES.filter((source) => (
    _liveTracks[source].preflight && _liveTracks[source].preflight.available
  ));
  const completedSources = LIVE_SOURCES.filter((source) => (
    _liveTracks[source].session && _liveTracks[source].session.status === "completed"
  ));
  const failedSources = LIVE_SOURCES.filter((source) => (
    _liveTracks[source].session && ["failed", "stale"].includes(_liveTracks[source].session.status)
  ));

  for (const source of LIVE_SOURCES) {
    const readiness = liveElement(source, "readiness");
    const preflight = _liveTracks[source].preflight;
    if (!readiness) continue;
    readiness.textContent = preflight
      ? preflight.available ? "Готов" : liveReasonText(preflight.reason)
      : "Проверка недоступна";
    readiness.className = preflight && preflight.available ? "ok-text" : "muted";
  }

  if (_liveGroupBusy) {
    badge.textContent = "Выполняется";
    badge.className = "badge warn";
    status.textContent = activeSources.length > 0 ? "Завершаем запись встречи..." : "Запускаем оба аудиоисточника...";
  } else if (activeSources.length === LIVE_SOURCES.length) {
    badge.textContent = "Запись";
    badge.className = "badge warn";
    status.textContent = "Микрофон и системный звук записываются. Не закрывайте страницу.";
  } else if (activeSources.length > 0) {
    badge.textContent = "Частичная запись";
    badge.className = "badge err";
    status.textContent = `Активен только ${activeSources.join(" + ")}. Остановите запись и повторите запуск.`;
  } else if (completedSources.length === LIVE_SOURCES.length) {
    badge.textContent = "Завершено";
    badge.className = "badge ok";
    status.textContent = "Черновик встречи сохранён. MIC и SYS исключены из индекса.";
  } else if (failedSources.length > 0) {
    badge.textContent = "Ошибка";
    badge.className = "badge err";
    status.textContent = "Один из источников завершился ошибкой. Проверьте устройства и повторите запись.";
  } else if (readySources.length === LIVE_SOURCES.length) {
    badge.textContent = "Готово";
    badge.className = "badge ok";
    status.textContent = "Микрофон и системный звук готовы к одновременной записи.";
  } else {
    badge.textContent = "Заблокировано";
    badge.className = "badge err";
    status.textContent = "Для запуска должны быть готовы и микрофон, и системный звук.";
  }

  const canStart = _permissions.has("jobs.start");
  const canStop = _permissions.has("jobs.cancel");
  start.disabled = _liveGroupBusy || activeSources.length > 0 || _activeJob !== null ||
    !canStart || readySources.length !== LIVE_SOURCES.length;
  stop.disabled = _liveGroupBusy || activeSources.length === 0 || !canStop;
  vad.disabled = _liveGroupBusy || activeSources.length > 0;
  force.disabled = _liveGroupBusy || activeSources.length > 0;
  if (!canStart) start.title = "Недостаточно прав: jobs.start";
  else if (_activeJob !== null) start.title = "Сначала остановите offline-обработку";
  else if (readySources.length !== LIVE_SOURCES.length) start.title = "Оба аудиоисточника должны быть готовы";
  else start.title = "Одновременно запустить MIC и SYS";
  stop.title = canStop ? "Остановить и финализировать обе дорожки" : "Недостаточно прав: jobs.cancel";

  const partials = LIVE_SOURCES.map((source) => ({ source, text: _liveTracks[source].partial.trim() }))
    .filter((item) => item.text);
  partial.textContent = partials.length > 0
    ? partials.map((item) => `${item.source}: ${item.text}`).join(" · ")
    : activeSources.length > 0 ? "Ожидание речи..." : "Нет активного фрагмента";
  renderLiveWarnings();
  renderLiveConversation();
  updateLiveElapsed();
}

async function liveResponseMessage(resp, fallback) {
  if (resp.status === 401) return "Your login session expired. Sign in again.";
  if (resp.status === 403) return "You do not have permission for this live action.";
  let code = "";
  try {
    const body = await resp.json();
    if (body && body.detail && typeof body.detail === "object") code = String(body.detail.code || "");
  } catch (e) { /* controlled fallback below */ }
  return LIVE_REASON_TEXT[code] || fallback;
}

async function refreshLivePreflight(source) {
  const state = _liveTracks[source];
  const device = selectedLiveDevice(source);
  const query = new URLSearchParams({ source });
  if (device !== null) query.set("audio_device_index", String(device));
  let resp;
  try {
    resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/live/preflight?${query.toString()}`
    );
  } catch (e) {
    state.preflight = null;
    state.devicesRevision += 1;
    setLiveError(source, "Could not reach the local live transcription API.");
    renderLiveTrack(source);
    return;
  }
  if (!resp) {
    state.preflight = null;
    state.devicesRevision += 1;
    renderLiveTrack(source);
    return;
  }
  if (!resp.ok) {
    state.preflight = null;
    state.devicesRevision += 1;
    setLiveError(source, await liveResponseMessage(resp, "Could not check live source readiness."));
    renderLiveTrack(source);
    return;
  }
  state.preflight = await resp.json();
  state.devicesRevision += 1;
  setLiveError(source, "");
  renderLiveTrack(source);
}

function resetLiveEvents(source, session) {
  const state = _liveTracks[source];
  if (state.session && state.session.session_id === session.session_id) {
    state.session = session;
    return;
  }
  state.session = session;
  state.cursor = 0;
  state.partial = "";
  state.finals = [];
  state.finalsRevision += 1;
}

async function loadActiveLiveSession(source) {
  const state = _liveTracks[source];
  const query = new URLSearchParams({ source });
  let resp;
  try {
    resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/live/sessions/active?${query.toString()}`
    );
  } catch (e) {
    setLiveError(source, "Could not load active live session state.");
    return;
  }
  if (!resp || !resp.ok) return;
  const body = await resp.json();
  if (body.session) {
    if (body.session.source !== source) {
      setLiveError(source, "Live session source did not match this track.");
      return;
    }
    resetLiveEvents(source, body.session);
  } else if (liveIsActive(state.session)) {
    const statusResp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/live/sessions/${encodeURIComponent(state.session.session_id)}`
    );
    if (statusResp && statusResp.ok) state.session = await statusResp.json();
  }
  renderLiveTrack(source);
}

function applyLiveEvents(source, events) {
  const state = _liveTracks[source];
  const batchSeen = new Set();
  for (const event of events) {
    const eventId = Number(event.event_id);
    if (!Number.isInteger(eventId) || eventId <= state.cursor || batchSeen.has(eventId)) continue;
    if (event.source && event.source !== source) continue;
    batchSeen.add(eventId);
    if (event.type === "partial") {
      state.partial = String(event.text || "");
    } else if (event.type === "final") {
      state.partial = "";
      const text = String(event.text || "").trim();
      if (text) {
        state.finals.push({
          eventId,
          segmentId: String(event.segment_id || `event-${eventId}`),
          source,
          text,
          start: Number(event.start) || 0,
          end: Number(event.end) || 0,
        });
        if (state.finals.length > LIVE_FINAL_ROWS_MAX) {
          state.finals.splice(0, state.finals.length - LIVE_FINAL_ROWS_MAX);
        }
        state.finalsRevision += 1;
      }
    }
  }
}

async function pollLiveTrack(source) {
  const state = _liveTracks[source];
  if (!state.session || !state.session.session_id) return;
  const wasActive = liveIsActive(state.session);
  const sessionId = encodeURIComponent(state.session.session_id);
  const prefix = `/meetings/${encodeURIComponent(MEETING_ID)}/live/sessions/${sessionId}`;
  const [eventsResp, statusResp] = await Promise.all([
    apiFetch(`${prefix}/events?after=${state.cursor}&limit=200`),
    apiFetch(prefix),
  ]);
  if (!eventsResp || !statusResp || !eventsResp.ok || !statusResp.ok) {
    throw new Error("live_poll_failed");
  }
  const payload = await eventsResp.json();
  applyLiveEvents(source, Array.isArray(payload.events) ? payload.events : []);
  const next = Number(payload.next_after);
  if (Number.isInteger(next) && next >= state.cursor) state.cursor = next;
  if (payload.truncated) setLiveError(source, "Older live events were compacted; the newest draft remains available.");
  state.session = await statusResp.json();
  if (state.session && !state.session.is_active) state.partial = "";
  renderLiveTrack(source);
  if (wasActive && !liveIsActive(state.session)) await loadLiveTimeline();
}

function stopLiveTimersIfIdle() {
  const active = LIVE_SOURCES.some((source) => liveIsActive(_liveTracks[source].session));
  if (active) return;
  if (_livePollTimer) clearInterval(_livePollTimer);
  if (_liveClockTimer) clearInterval(_liveClockTimer);
  _livePollTimer = null;
  _liveClockTimer = null;
}

function startLiveTimers() {
  if (!_livePollTimer) _livePollTimer = setInterval(pollLiveSessions, LIVE_POLL_INTERVAL_MS);
  if (!_liveClockTimer) _liveClockTimer = setInterval(updateLiveElapsed, 1000);
}

async function pollLiveSessions() {
  if (_livePollInFlight) return;
  _livePollInFlight = true;
  try {
    await Promise.all(
      LIVE_SOURCES.filter((source) => liveIsActive(_liveTracks[source].session))
        .map((source) => pollLiveTrack(source))
    );
    setLiveGlobalError("");
  } catch (e) {
    setLiveGlobalError("Live status refresh failed. The page will retry automatically.");
  } finally {
    _livePollInFlight = false;
    stopLiveTimersIfIdle();
  }
}

async function loadLive() {
  setLiveGlobalError("");
  await Promise.all([
    loadLiveTimeline(),
    ...LIVE_SOURCES.flatMap((source) => [
      refreshLivePreflight(source),
      loadActiveLiveSession(source),
    ]),
  ]);
  if (LIVE_SOURCES.some((source) => liveIsActive(_liveTracks[source].session))) {
    startLiveTimers();
    await pollLiveSessions();
  }
}

async function startLiveCapture() {
  if (_liveGroupBusy || anyLiveActive()) return;
  if (_activeJob !== null) {
    setLiveGlobalError("Сначала остановите offline-обработку встречи.");
    return;
  }
  if (LIVE_SOURCES.some((source) => (
    !_liveTracks[source].preflight || !_liveTracks[source].preflight.available
  ))) {
    setLiveGlobalError("Для запуска должны быть готовы и микрофон, и системный звук.");
    return;
  }
  setLiveGlobalError("");
  const csrf = await ensureCsrf();
  if (!csrf) {
    setLiveGlobalError("Не удалось получить CSRF-токен. Войдите снова.");
    return;
  }
  _liveGroupBusy = true;
  renderLiveCapture();
  const body = {
    mic_audio_device_index: selectedLiveDevice("MIC"),
    sys_audio_device_index: selectedLiveDevice("SYS"),
    vad: document.getElementById("live-vad").value,
    force: document.getElementById("live-force").checked,
  };
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/live/capture`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
      }
    );
    if (!resp) return;
    if (!resp.ok) {
      setLiveGlobalError(await liveResponseMessage(resp, "Не удалось запустить запись встречи."));
      await Promise.all(LIVE_SOURCES.map((source) => loadActiveLiveSession(source)));
      return;
    }
    const payload = await resp.json();
    for (const source of LIVE_SOURCES) {
      if (payload.sessions && payload.sessions[source]) {
        resetLiveEvents(source, payload.sessions[source]);
      }
    }
    document.getElementById("live-force").checked = false;
    startLiveTimers();
    await pollLiveSessions();
    await refreshJobs();
  } catch (e) {
    setLiveGlobalError("Запись встречи не запущена. Проверьте локальный API.");
    await Promise.all(LIVE_SOURCES.map((source) => loadActiveLiveSession(source)));
  } finally {
    _liveGroupBusy = false;
    renderLiveCapture();
  }
}

async function stopLiveCapture() {
  if (_liveGroupBusy || !anyLiveActive()) return;
  setLiveGlobalError("");
  const csrf = await ensureCsrf();
  if (!csrf) {
    setLiveGlobalError("Не удалось получить CSRF-токен. Войдите снова.");
    return;
  }
  _liveGroupBusy = true;
  renderLiveCapture();
  try {
    const resp = await apiFetch(
      `/meetings/${encodeURIComponent(MEETING_ID)}/live/capture/stop`,
      { method: "POST", headers: { "X-CSRF-Token": csrf } }
    );
    if (!resp) return;
    if (!resp.ok) {
      setLiveGlobalError(await liveResponseMessage(resp, "Не удалось полностью остановить запись."));
    } else {
      const payload = await resp.json();
      for (const source of LIVE_SOURCES) {
        if (payload.sessions && payload.sessions[source]) {
          _liveTracks[source].session = payload.sessions[source];
          if (!liveIsActive(payload.sessions[source])) _liveTracks[source].partial = "";
        }
      }
    }
    await Promise.all(LIVE_SOURCES.map((source) => loadActiveLiveSession(source)));
    await Promise.all([loadMeeting(), loadArtifacts(), loadLiveTimeline(), refreshJobs()]);
  } catch (e) {
    setLiveGlobalError("Запись остановлена не полностью. Обновите состояние Live.");
  } finally {
    _liveGroupBusy = false;
    renderLiveCapture();
    stopLiveTimersIfIdle();
  }
}

// ---- speaker mapping ----
async function loadSpeakerMapping() {
  const panel = document.getElementById("speaker-map-panel");
  const status = document.getElementById("speaker-map-status");
  const saveButton = document.getElementById("speaker-map-save-btn");
  const canEdit = _permissions.has("meetings.edit");
  saveButton.hidden = !canEdit;
  saveButton.disabled = !canEdit;
  if (status) {
    status.textContent = "";
    status.classList.remove("err");
  }
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/speakers`);
  if (!resp) { panel.replaceChildren(); return; }
  if (!resp.ok) {
    panel.replaceChildren(_mkEmptyMsg("Сопоставление спикеров недоступно"));
    return;
  }
  const data = await resp.json();
  _speakerRows = data.speakers || [];
  if (_speakerRows.length === 0) {
    panel.replaceChildren(_mkEmptyMsg("Метки спикеров пока не найдены"));
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
    name.placeholder = "Имя";
    name.value = sp.name || "";
    name.dataset.field = "name";
    name.disabled = !canEdit;

    const role = document.createElement("input");
    role.type = "text";
    role.maxLength = 120;
    role.placeholder = "Роль";
    role.value = sp.role || "";
    role.dataset.field = "role";
    role.disabled = !canEdit;

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
      status.textContent = "Требуется вход";
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
      status.textContent = "Не удалось сохранить сопоставление";
      status.classList.add("err");
    }
    return;
  }
  await Promise.all([loadSpeakerMapping(), loadTranscript()]);
  if (status) {
    status.textContent = "Сохранено";
    status.classList.remove("err");
  }
}

// ---- artifacts ----
async function loadArtifacts() {
  const panel = document.getElementById("artifacts-panel");
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts`);
  if (!resp) { panel.replaceChildren(); return; }
  if (!resp.ok) { panel.replaceChildren(_mkEmptyMsg("Артефакты недоступны")); return; }
  const data = await resp.json();
  const artifacts = (data.artifacts || []).filter(a => a.exists);
  if (artifacts.length === 0) {
    panel.replaceChildren(_mkEmptyMsg("Артефакты пока не созданы"));
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
    btn.textContent = "Открыть";
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
  setWorkspaceTab("artifacts");
  const viewer = document.getElementById("artifact-viewer");
  if (!viewer) return;
  const loading = _mkEl("div", "artifact-content");
  loading.textContent = "Загрузка...";
  viewer.replaceChildren(loading);
  document.getElementById("close-artifact-btn").hidden = false;
  const resp = await apiFetch(`/meetings/${encodeURIComponent(MEETING_ID)}/artifacts/${encodeURIComponent(key)}`);
  if (!resp || !resp.ok) {
    const errDiv = _mkEl("div", "err-msg");
    errDiv.textContent = "Не удалось загрузить артефакт.";
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
    if (d.detail && typeof d.detail === "object" && typeof d.detail.message === "string") {
      return d.detail.message.slice(0, 240);
    }
  } catch (e) { /* not JSON */ }
  return null;
}

async function loadPermissions() {
  const resp = await fetch("/auth/me");
  if (resp.status === 401) {
    show401();
    _permissions = new Set();
    document.getElementById("hdr-admin-link").hidden = true;
    return;
  }
  if (!resp.ok) {
    _permissions = new Set();
    document.getElementById("hdr-admin-link").hidden = true;
    const auth = document.getElementById("hdr-auth");
    if (auth) {
      auth.textContent = "Авторизация недоступна";
      auth.className = "badge warn";
    }
    return;
  }
  const d = await resp.json();
  _permissions = new Set(Array.isArray(d.permissions) ? d.permissions : []);
  document.getElementById("hdr-admin-link").hidden = !_permissions.has("users.manage");
  hideAuthOverlay();
  const auth = document.getElementById("hdr-auth");
  if (auth) {
    const roles = Array.isArray(d.roles) && d.roles.length ? d.roles.join(", ") : "user";
    const label = d.email || "local user";
    auth.textContent = `${label} · ${roles}`;
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
  const liveBusy = anyLiveActive();
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
      forceBtn.textContent = "Перезапустить принудительно";
      forceBtn.dataset.stage = st.stage;
      forceBtn.disabled = !canRetry || _activeJob !== null || _actionInProgress || liveBusy;
      forceBtn.title = !canRetry
        ? "Permission required: jobs.retry"
        : liveBusy
          ? "Stop live capture before running pipeline stages"
          : "Stage output already exists; this re-runs it from scratch";
      forceBtn.addEventListener("click", () => retryStage(forceBtn.dataset.stage, true));
      actions.appendChild(forceBtn);
    } else if (ready && ready.state === "ready_for_retry") {
      const retryBtn = document.createElement("button");
      retryBtn.className = "primary";
      retryBtn.textContent = "Повторить";
      retryBtn.dataset.stage = st.stage;
      retryBtn.disabled = !canRetry || _activeJob !== null || _actionInProgress || liveBusy;
      if (!canRetry) retryBtn.title = "Permission required: jobs.retry";
      else if (liveBusy) retryBtn.title = "Stop live capture before running pipeline stages";
      retryBtn.addEventListener("click", () => retryStage(retryBtn.dataset.stage, false));
      actions.appendChild(retryBtn);
    } else {
      const startBtn = document.createElement("button");
      startBtn.className = "primary";
      startBtn.textContent = "Запустить";
      startBtn.dataset.stage = st.stage;
      const blocked = ready ? ready.can_run === false : false;
      startBtn.disabled = !canStart || blocked || _activeJob !== null || _actionInProgress || liveBusy;
      if (!canStart) startBtn.title = "Permission required: jobs.start";
      else if (blocked) startBtn.title = ready.detail || "Stage is blocked";
      else if (_activeJob !== null) startBtn.title = "Another job is already running";
      else if (liveBusy) startBtn.title = "Stop live capture before running pipeline stages";
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
  const busy = _activeJob !== null || _actionInProgress || anyLiveActive();

  const states = Object.values(_readiness);
  const anyDone = states.some((s) => s.state === "done");
  const anyPending = states.some((s) => s.state !== "done");

  const runBtn = document.createElement("button");
  runBtn.className = "primary";
  runBtn.textContent = "Запустить полный цикл";
  runBtn.disabled = !canStart || busy;
  if (!canStart) runBtn.title = "Permission required: jobs.start";
  runBtn.addEventListener("click", () => startPipeline({ profile: "full" }));
  box.appendChild(runBtn);

  if (anyDone && anyPending) {
    const resumeBtn = document.createElement("button");
    resumeBtn.textContent = "Продолжить цикл";
    resumeBtn.disabled = !canStart || busy;
    resumeBtn.title = "Continue: done stages are skipped, execution starts at the first pending stage";
    resumeBtn.addEventListener("click", () => startPipeline({ profile: "full", resume: true }));
    box.appendChild(resumeBtn);
  }

  if (_failedStage) {
    const retryBtn = document.createElement("button");
    retryBtn.textContent = "Повторить сбойный этап";
    retryBtn.dataset.stage = _failedStage;
    retryBtn.disabled = !canRetry || busy;
    if (!canRetry) retryBtn.title = "Permission required: jobs.retry";
    retryBtn.addEventListener("click", () => retryStage(retryBtn.dataset.stage, false));
    box.appendChild(retryBtn);
  }
}

// Quick links to results that already exist (manifest-driven).
function renderResults() {
  const boxes = [
    document.getElementById("pipeline-results"),
    document.getElementById("overview-results"),
  ].filter(Boolean);
  boxes.forEach((box) => { box.textContent = ""; });
  const targets = [
    { key: "segments", label: "Транскрипт", tab: "transcript" },
    { key: "speaker_transcript", label: "Спикеры", tab: "transcript" },
    { key: "memo", label: "Резюме", tab: "artifacts" },
    { key: "protocol", label: "Протокол", tab: "artifacts" },
    { key: "tasks", label: "Задачи", tab: "artifacts" },
  ];
  let count = 0;
  for (const tgt of targets) {
    const entry = manifestEntry(tgt.key);
    if (!entry || !entry.exists) continue;
    count += 1;
    boxes.forEach((box) => {
      const chip = document.createElement("button");
      chip.className = "result-chip";
      chip.textContent = tgt.label + " ✓";
      chip.dataset.tab = tgt.tab;
      chip.addEventListener("click", () => setWorkspaceTab(chip.dataset.tab));
      box.appendChild(chip);
    });
  }
  if (count === 0) {
    boxes.forEach((box) => {
      const empty = document.createElement("span");
      empty.className = "empty";
      empty.textContent = "Результаты ещё не созданы";
      box.appendChild(empty);
    });
  }
  const next = document.getElementById("overview-next");
  if (next) {
    const states = Object.values(_readiness || {});
    const failed = states.find((entry) => entry.state === "ready_for_retry");
    const blocked = states.find((entry) => entry.state === "blocked");
    next.textContent = failed
      ? "Предыдущая стадия завершилась ошибкой. Откройте обработку и выполните Retry."
      : blocked
        ? `Следующая стадия заблокирована: ${blocked.detail || blocked.reason || "проверьте preflight"}.`
        : count >= 4
          ? "Основные результаты готовы. Проверьте протокол и пункты needs_review."
          : "Продолжите pipeline, чтобы получить транскрипт, протокол и поиск по встрече.";
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
  if (anyLiveActive()) { setJobsError("Stop live capture before running pipeline stages."); return; }
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
  if (anyLiveActive()) { setJobsError("Stop live capture before running the offline pipeline."); return; }
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
  if (anyLiveActive()) { setJobsError("Stop live capture before retrying pipeline stages."); return; }
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
  renderLiveCapture();
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
  await loadStages();
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
  if (mode === "vector") return "поиск: семантический (vector)";
  if (mode === "lexical") return "поиск: лексический";
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
  setText("qa-search-status", "Поиск...");
  const csrf = await ensureCsrf();
  if (!csrf) {
    setText("qa-search-status", "");
    setText("qa-search-error", "Не удалось получить CSRF-токен. Войдите снова.");
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
    setText("qa-search-error", "Запрос поиска не выполнен. Повторите попытку.");
    return;
  }
  if (!resp) return;  // 401 handled by overlay
  if (!resp.ok) {
    setText("qa-search-status", "");
    setText("qa-search-error", await describeError(resp, "Поиск не выполнен."));
    return;
  }
  const data = await resp.json();
  const results = Array.isArray(data.results) ? data.results : [];
  setText("qa-search-status", results.length ? "" : "Совпадений в этой встрече нет.");
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
  await loadPermissions();
  await Promise.all([
    loadMeeting(),
    loadMedia(),
    loadTranscript(),
    loadSpeakerMapping(),
    loadArtifacts(),
    loadJobs(),
    loadLive(),
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

const _liveRefreshBtn = document.getElementById("live-refresh-btn");
if (_liveRefreshBtn) _liveRefreshBtn.addEventListener("click", loadLive);
const _liveStartBtn = document.getElementById("live-start-btn");
if (_liveStartBtn) _liveStartBtn.addEventListener("click", startLiveCapture);
const _liveStopBtn = document.getElementById("live-stop-btn");
if (_liveStopBtn) _liveStopBtn.addEventListener("click", stopLiveCapture);
document.querySelectorAll("[data-live-device]").forEach((select) => {
  select.addEventListener("change", () => refreshLivePreflight(select.dataset.liveDevice));
});

const _qaAskBtn = document.getElementById("qa-ask-btn");
if (_qaAskBtn) _qaAskBtn.addEventListener("click", askQuestion);
const _qaSearchBtn = document.getElementById("qa-search-btn");
if (_qaSearchBtn) _qaSearchBtn.addEventListener("click", meetingSearch);
const _qaSearchInput = document.getElementById("qa-search-input");
if (_qaSearchInput) {
  _qaSearchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") meetingSearch(); });
}

document.querySelectorAll("[data-workspace-tab]").forEach((button) => {
  button.addEventListener("click", () => setWorkspaceTab(button.dataset.workspaceTab));
});
document.querySelectorAll("[data-open-tab]").forEach((button) => {
  button.addEventListener("click", () => setWorkspaceTab(button.dataset.openTab));
});
const _workspaceMenu = document.getElementById("workspace-menu");
if (_workspaceMenu) {
  _workspaceMenu.addEventListener("click", () => {
    document.getElementById("workspace-nav").classList.toggle("open");
  });
}

setWorkspaceTab(_activeWorkspaceTab);
reloadAll();
