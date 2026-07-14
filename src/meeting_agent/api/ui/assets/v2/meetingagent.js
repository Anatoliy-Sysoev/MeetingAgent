"use strict";

const PIPELINE_STAGES = [
  ["extract_audio", "Извлечение аудио", "Нормализация в WAV 16 кГц mono"],
  ["transcribe", "Транскрибация", "Faster Whisper или GigaAM"],
  ["diarize", "Диаризация", "Разделение голосов"],
  ["merge", "Объединение", "Транскрипт и спикеры"],
  ["chunk", "Чанкинг", "Окна для поиска"],
  ["enrich", "Обогащение", "Темы и смысловые типы"],
  ["index", "Индексация", "Meeting Q&A"],
  ["analyze", "Анализ", "Протокол и задачи"],
];

const state = {
  csrf: null,
  user: null,
  permissions: new Set(),
  meetings: [],
  activeJob: null,
  activeSection: "meetings",
};

const pageTitles = {
  meetings: ["Встречи", "MeetingAgent / Встречи", "/MeetingAgent"],
  "new-meeting": ["Новая встреча", "MeetingAgent / Новая встреча", "/MeetingAgent/new"],
  operations: ["Обработка", "MeetingAgent / Обработка", "/MeetingAgent/processing"],
};

function byId(id) {
  return document.getElementById(id);
}

function showMessage(text, kind) {
  const el = byId("message");
  el.textContent = text || "";
  el.className = "banner";
  if (text) {
    el.classList.add("visible");
    if (kind) el.classList.add(kind);
  }
}

async function safeJson(resp) {
  try {
    return await resp.json();
  } catch {
    return null;
  }
}

function describeError(resp, data) {
  if (resp.status === 401) return "Сессия отсутствует или завершена. Войдите снова.";
  if (resp.status === 403) return "Недостаточно прав или устарел CSRF-токен. Обновите вход.";
  if (resp.status === 409 && data && data.duplicate) return "Такая запись уже загружена.";
  if (resp.status === 413) return "Файл превышает допустимый размер.";
  if (resp.status === 429) return "Слишком много попыток. Повторите позже.";
  if (data && typeof data.detail === "string") return data.detail.slice(0, 240);
  if (data && data.detail && typeof data.detail.message === "string") {
    return data.detail.message.slice(0, 240);
  }
  if (data && data.detail && typeof data.detail.error === "string") {
    return data.detail.error.slice(0, 240);
  }
  return `Ошибка HTTP ${resp.status}`;
}

async function apiFetch(url, opts) {
  const resp = await fetch(url, opts);
  if (!resp.ok) {
    const data = await safeJson(resp);
    throw new Error(describeError(resp, data));
  }
  return resp;
}

async function getCsrfToken() {
  const resp = await fetch("/auth/csrf");
  if (!resp.ok) return null;
  const data = await safeJson(resp);
  return data ? data.csrf_token : null;
}

function roleLabel(user) {
  const roles = Array.isArray(user && user.roles) ? user.roles : [];
  if (roles.includes("admin")) return "Администратор";
  if (roles.includes("editor")) return "Редактор";
  if (roles.includes("viewer")) return "Наблюдатель";
  return "Пользователь";
}

function applyPermissions() {
  const canWrite = state.permissions.has("jobs.start") || state.permissions.has("meetings.edit");
  document.querySelectorAll("[data-write-control]").forEach((element) => {
    element.hidden = !canWrite;
  });
}

async function refreshAuth() {
  const status = byId("authStatus");
  const loginPanel = byId("loginPanel");
  const resp = await fetch("/auth/me");
  if (!resp.ok) {
    state.user = null;
    state.permissions = new Set();
    byId("adminNav").hidden = true;
    status.textContent = "Вход не выполнен";
    byId("railRole").textContent = "Гость";
    byId("railAccount").textContent = "Только форма входа";
    loginPanel.classList.add("visible");
    applyPermissions();
    return;
  }
  const data = await safeJson(resp);
  state.user = data;
  state.permissions = new Set(Array.isArray(data && data.permissions) ? data.permissions : []);
  const role = roleLabel(data);
  byId("adminNav").hidden = !state.permissions.has("users.manage");
  status.textContent = role;
  byId("railRole").textContent = role;
  byId("railAccount").textContent = data.email || "local user";
  loginPanel.classList.remove("visible");
  applyPermissions();
}

async function doLogin() {
  const email = byId("loginEmail").value.trim();
  const password = byId("loginPassword").value;
  const resp = await fetch("/auth/local/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    showMessage(resp.status === 429 ? "Слишком много попыток входа. Повторите позже." : "Войти не удалось. Проверьте логин и пароль.", "error");
    return;
  }
  state.csrf = null;
  byId("loginPassword").value = "";
  await refreshAuth();
  await Promise.all([loadMeetings(), loadActiveJob()]);
  showMessage("Вход выполнен.", "ok");
}

function createMode(mode) {
  document.querySelectorAll("[data-create-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.createMode === mode);
  });
  document.querySelectorAll("[data-create-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.createPanel !== mode;
  });
  if (mode === "live") byId("liveMeetingTitle").focus();
}

function setSection(section, updateHistory = true) {
  const target = pageTitles[section] ? section : "meetings";
  state.activeSection = target;
  for (const el of document.querySelectorAll("[id^='section-']")) {
    el.hidden = el.id !== `section-${target}`;
  }
  for (const btn of document.querySelectorAll(".nav-item")) {
    const active = btn.dataset.section === target;
    btn.classList.toggle("active", active);
    if (active) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  }
  const meta = pageTitles[target];
  byId("pageTitle").textContent = meta[0];
  byId("breadcrumbs").textContent = meta[1];
  byId("productNav").classList.remove("open");
  if (updateHistory && window.location.pathname !== meta[2]) window.history.pushState({ section: target }, "", meta[2]);
  if (target === "operations") loadActiveJob();
}

function meetingSourceName(item) {
  if (item.source_kind === "live_session") return "Live";
  if (Number(item.media_count) > 0) return "Видео / аудио";
  return "Без файла";
}

function normalizedStatus(item) {
  return String(item.processing_status || item.status || "uploaded").toLowerCase();
}

function statusView(status) {
  if (["analyzed", "complete", "completed", "indexed"].includes(status)) return ["Готово", "success", "ready"];
  if (["failed", "error"].includes(status)) return ["Нужен повтор", "error", "error"];
  if (["processing", "transcribing", "diarizing", "running", "starting"].includes(status)) return ["В работе", "running", "running"];
  if (["live", "recording"].includes(status)) return ["Идёт запись", "live", "running"];
  if (["transcribed", "diarized", "merged", "chunked", "enriched"].includes(status)) return [status === "transcribed" ? "Транскрипт готов" : "Частично готово", "running", "running"];
  return ["Загружено", "neutral", "uploaded"];
}

function stageIndexFor(item) {
  const status = normalizedStatus(item);
  const direct = {
    audio_extracted: 1,
    transcribed: 2,
    diarized: 3,
    merged: 4,
    chunked: 5,
    enriched: 6,
    indexed: 7,
    analyzed: 8,
    complete: 8,
    completed: 8,
  };
  let index = direct[status] || 0;
  const keys = new Set(Array.isArray(item.artifact_keys) ? item.artifact_keys : []);
  if (keys.has("segments")) index = Math.max(index, 2);
  if (keys.has("diarization")) index = Math.max(index, 3);
  if (keys.has("speaker_transcript")) index = Math.max(index, 4);
  if (keys.has("chunks")) index = Math.max(index, 5);
  if (keys.has("enriched_chunks")) index = Math.max(index, 6);
  if (keys.has("index_status")) index = Math.max(index, 7);
  if (keys.has("protocol") || keys.has("memo")) index = Math.max(index, 8);
  if (state.activeJob && state.activeJob.meeting_id === item.meeting_id) {
    const stage = state.activeJob.stage || state.activeJob.current_stage;
    const activeIndex = PIPELINE_STAGES.findIndex((entry) => entry[0] === stage);
    if (activeIndex >= 0) index = Math.max(index, activeIndex);
  }
  return Math.min(index, 8);
}

function resultLabel(item) {
  const keys = new Set(Array.isArray(item.artifact_keys) ? item.artifact_keys : []);
  const labels = [];
  if (keys.has("segments")) labels.push("Транскрипт");
  if (keys.has("protocol")) labels.push("Протокол");
  if (keys.has("tasks")) labels.push("Задачи");
  if (keys.has("risks")) labels.push("Риски");
  return labels.length ? labels.join(" · ") : "Нет";
}

function inSelectedPeriod(item, value) {
  if (!value || value === "all") return true;
  const raw = item.date || item.created_at;
  const date = raw ? new Date(raw) : null;
  if (!date || Number.isNaN(date.getTime())) return false;
  const now = new Date();
  if (value === "today") return date.toDateString() === now.toDateString();
  const days = Number(value);
  return now.getTime() - date.getTime() <= days * 86400000;
}

function filteredMeetings() {
  const query = byId("meetingSearch").value.trim().toLowerCase();
  const statusFilter = byId("meetingStatusFilter").value;
  const period = byId("meetingPeriodFilter").value;
  return state.meetings.filter((item) => {
    const haystack = `${item.title || ""} ${item.meeting_id || ""} ${item.date || ""}`.toLowerCase();
    const statusGroup = statusView(normalizedStatus(item))[2];
    return (!query || haystack.includes(query)) && (!statusFilter || statusFilter === statusGroup) && inSelectedPeriod(item, period);
  });
}

function appendCell(row, label, content) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  if (typeof content === "string") cell.textContent = content;
  else cell.append(content);
  row.append(cell);
  return cell;
}

function renderMeetings() {
  const items = filteredMeetings();
  const tbody = byId("meetingsTable");
  tbody.replaceChildren();
  byId("meetingsCount").textContent = `${items.length} из ${state.meetings.length}`;
  byId("meetingsRange").textContent = items.length ? `1–${items.length} из ${state.meetings.length}` : "0 записей";
  byId("meetingsEmpty").hidden = items.length > 0;

  for (const item of items) {
    const row = document.createElement("tr");
    const titleWrap = document.createElement("div");
    const open = document.createElement("a");
    open.className = "meeting-title";
    open.href = item.workspace_url || `/meetings/${encodeURIComponent(item.meeting_id)}/workspace`;
    open.textContent = item.title || item.meeting_id;
    const id = document.createElement("div");
    id.className = "meeting-id";
    id.textContent = item.meeting_id || "";
    titleWrap.append(open, id);
    appendCell(row, "Встреча", titleWrap);
    appendCell(row, "Дата", item.date || "—");
    appendCell(row, "Источник", meetingSourceName(item));

    const progress = document.createElement("div");
    const stageIndex = stageIndexFor(item);
    const stageText = document.createElement("span");
    stageText.className = "stage-text";
    stageText.textContent = `${stageIndex} / 8`;
    const bar = document.createElement("div");
    bar.className = "micro-progress";
    const fill = document.createElement("span");
    fill.className = `progress-step-${stageIndex}`;
    bar.append(fill);
    progress.append(stageText, bar);
    appendCell(row, "Прогресс", progress);

    const statusInfo = statusView(normalizedStatus(item));
    const badge = document.createElement("span");
    badge.className = `status ${statusInfo[1]}`;
    badge.textContent = statusInfo[0];
    appendCell(row, "Статус", badge);

    const results = document.createElement("span");
    results.className = resultLabel(item) === "Нет" ? "muted" : "result-links";
    results.textContent = resultLabel(item);
    appendCell(row, "Результаты", results);

    const actions = document.createElement("div");
    actions.className = "row-actions";
    const workspace = document.createElement("a");
    workspace.className = "button-link";
    workspace.href = item.workspace_url || `/meetings/${encodeURIComponent(item.meeting_id)}/workspace`;
    workspace.textContent = "Открыть";
    actions.append(workspace);
    if (state.permissions.has("jobs.start")) {
      const transcript = document.createElement("button");
      transcript.type = "button";
      transcript.textContent = "Транскрипт";
      transcript.addEventListener("click", () => startPipeline(item.meeting_id, "transcript_only"));
      const full = document.createElement("button");
      full.type = "button";
      full.textContent = "Полный цикл";
      full.addEventListener("click", () => startPipeline(item.meeting_id, "full"));
      actions.append(transcript, full);
    }
    appendCell(row, "Действия", actions);
    tbody.append(row);
  }
}

async function loadMeetings() {
  try {
    const resp = await apiFetch("/meetings?limit=200");
    const data = await safeJson(resp);
    state.meetings = Array.isArray(data && data.items) ? data.items : [];
    renderMeetings();
    if (Array.isArray(data && data.errors) && data.errors.length) {
      showMessage(`Часть карточек не прочитана: ${data.errors.length}.`, "error");
    }
  } catch (err) {
    state.meetings = [];
    renderMeetings();
    showMessage(err.message || "Не удалось загрузить встречи.", "error");
  }
}

function renderUploadResult(data, action) {
  const panel = byId("uploadResult");
  panel.replaceChildren();
  const title = document.createElement("div");
  title.className = "meeting-title";
  title.textContent = data.title || data.meeting_id;
  const id = document.createElement("div");
  id.className = "meeting-id";
  id.textContent = data.meeting_id;
  const actions = document.createElement("div");
  actions.className = "actions";
  const open = document.createElement("a");
  open.className = "button-link";
  open.href = data.workspace_url || `/meetings/${encodeURIComponent(data.meeting_id)}/workspace`;
  open.textContent = "Открыть Workspace";
  actions.append(open);
  if (action === "none") {
    const transcript = document.createElement("button");
    transcript.type = "button";
    transcript.textContent = "Запустить транскрибацию";
    transcript.addEventListener("click", () => startPipeline(data.meeting_id, "transcript_only"));
    const full = document.createElement("button");
    full.type = "button";
    full.className = "primary";
    full.textContent = "Запустить полный цикл";
    full.addEventListener("click", () => startPipeline(data.meeting_id, "full"));
    actions.append(transcript, full);
  }
  panel.append(title, id, actions);
}

function selectedProfile() {
  return byId("postUploadAction").value || "full";
}

function syncSelectedProfile() {
  const selected = document.querySelector('input[name="profile-choice"]:checked');
  const value = selected ? selected.value : "full";
  byId("postUploadAction").value = value;
  return value;
}

async function uploadMeeting(event) {
  event.preventDefault();
  state.csrf = state.csrf || await getCsrfToken();
  if (!state.csrf) {
    showMessage("Нужно войти в систему перед загрузкой записи.", "error");
    return;
  }
  const form = byId("uploadForm");
  const fd = new FormData(form);
  const action = selectedProfile();
  if (!fd.get("title")) fd.delete("title");
  if (!fd.get("date")) fd.delete("date");
  fd.delete("profile-choice");
  const submit = byId("uploadSubmit");
  submit.disabled = true;
  showMessage("Загружаю запись и создаю карточку...", null);
  try {
    const resp = await apiFetch("/meetings/ingest", {
      method: "POST",
      headers: { "X-CSRF-Token": state.csrf },
      body: fd,
    });
    const data = await safeJson(resp);
    renderUploadResult(data, action);
    await loadMeetings();
    showMessage("Карточка встречи создана.", "ok");
    if (action !== "none") await startPipeline(data.meeting_id, action);
  } catch (err) {
    showMessage(err.message || "Загрузка не выполнена.", "error");
  } finally {
    submit.disabled = false;
  }
}

async function createLiveMeeting(event) {
  event.preventDefault();
  state.csrf = state.csrf || await getCsrfToken();
  if (!state.csrf) {
    showMessage("Нужно войти в систему перед созданием live-встречи.", "error");
    return;
  }
  const title = byId("liveMeetingTitle").value.trim();
  if (!title) {
    showMessage("Укажите название live-встречи.", "error");
    return;
  }
  const body = { title, language: byId("liveMeetingLanguage").value || "ru" };
  if (byId("liveMeetingDate").value) body.date = byId("liveMeetingDate").value;
  const submit = byId("liveMeetingSubmit");
  submit.disabled = true;
  showMessage("Создаю live-встречу...", null);
  try {
    const resp = await apiFetch("/meetings/live", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf },
      body: JSON.stringify(body),
    });
    const data = await safeJson(resp);
    const workspaceUrl = data && data.workspace_url;
    if (!workspaceUrl || !workspaceUrl.startsWith("/meetings/")) throw new Error("Сервер не вернул адрес Workspace.");
    showMessage("Live-встреча создана. Открываю Workspace...", "ok");
    window.location.assign(workspaceUrl);
  } catch (err) {
    submit.disabled = false;
    showMessage(err.message || "Live-встреча не создана.", "error");
  }
}

function selectedAsrEngine() {
  return byId("asrEngine") ? byId("asrEngine").value : "faster-whisper";
}

async function startPipeline(meetingId, profile) {
  state.csrf = state.csrf || await getCsrfToken();
  if (!state.csrf) {
    showMessage("Нужно войти в систему перед запуском обработки.", "error");
    return;
  }
  try {
    const resp = await apiFetch(`/meetings/${encodeURIComponent(meetingId)}/jobs/pipeline`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf },
      body: JSON.stringify({ profile, asr_engine: selectedAsrEngine() }),
    });
    const data = await safeJson(resp);
    showMessage(`Обработка запущена: ${data.job_id || data.pipeline_id || profile}`, "ok");
    await loadActiveJob();
    setSection("operations");
  } catch (err) {
    showMessage(err.message || "Обработка не запущена.", "error");
  }
}

function jobIsActive(job) {
  return Boolean(job && ["queued", "starting", "running", "cancelling"].includes(job.status));
}

function renderActiveBanner() {
  const box = byId("activeWork");
  if (!jobIsActive(state.activeJob)) {
    box.hidden = true;
    return;
  }
  const job = state.activeJob;
  const meeting = state.meetings.find((item) => item.meeting_id === job.meeting_id);
  const stage = job.stage || job.current_stage || "pipeline";
  const stageIndex = Math.max(0, PIPELINE_STAGES.findIndex((entry) => entry[0] === stage));
  byId("activeWorkTitle").textContent = `Обрабатывается: ${meeting ? meeting.title : job.meeting_id}`;
  byId("activeWorkDetail").textContent = `${PIPELINE_STAGES[stageIndex]?.[1] || stage}, этап ${stageIndex + 1} из 8`;
  byId("activeWorkProgress").className = `progress-step-${stageIndex}`;
  box.hidden = false;
}

function renderOperation(job) {
  const panel = byId("activeJobPanel");
  const stages = byId("operationStages");
  panel.replaceChildren();
  stages.replaceChildren();
  const active = jobIsActive(job);
  const currentStage = job && (job.stage || job.current_stage);
  const currentIndex = Math.max(0, PIPELINE_STAGES.findIndex((entry) => entry[0] === currentStage));
  const meeting = job && state.meetings.find((item) => item.meeting_id === job.meeting_id);
  byId("operationMeeting").textContent = job ? `${meeting ? meeting.title : job.meeting_id} · ${meeting ? meeting.date || "" : ""}` : "Локальный job runner";
  byId("operationStatus").textContent = active ? "В работе" : "Нет активной задачи";
  byId("operationStatus").className = `status ${active ? "running" : "neutral"}`;
  byId("operationProfile").textContent = job ? job.profile || job.kind || "stage" : "—";
  byId("operationProgressText").textContent = job ? `${currentIndex + 1} из 8 этапов` : "—";
  byId("operationStage").textContent = job ? PIPELINE_STAGES[currentIndex]?.[1] || currentStage || "—" : "—";
  byId("operationStarted").textContent = job ? job.started_at || job.created_at || "—" : "—";
  byId("operationProgress").className = `progress-step-${active ? currentIndex : 0}`;
  byId("operationCancel").hidden = !active || !state.permissions.has("jobs.cancel");
  byId("operationCancel").dataset.jobId = active ? job.job_id : "";
  byId("operationWorkspace").hidden = !job || !job.meeting_id;
  if (job && job.meeting_id) byId("operationWorkspace").href = `/meetings/${encodeURIComponent(job.meeting_id)}/workspace`;

  if (!job) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Активная задача не найдена. Запустите обработку из реестра или Workspace.";
    panel.append(empty);
  } else {
    [["Job", job.job_id], ["Встреча", job.meeting_id], ["Тип", job.kind || "stage"], ["Стадия", currentStage || "—"], ["Статус", job.status || "—"]].forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "job-kv";
      const label = document.createElement("b");
      label.textContent = key;
      const data = document.createElement("span");
      data.textContent = value || "—";
      row.append(label, data);
      panel.append(row);
    });
  }

  PIPELINE_STAGES.forEach((entry, index) => {
    const item = document.createElement("li");
    if (job && index < currentIndex) item.className = "done";
    else if (active && index === currentIndex) item.className = "active";
    const marker = document.createElement("span");
    marker.className = "stage-index";
    marker.textContent = String(index + 1);
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = entry[1];
    const detail = document.createElement("small");
    detail.textContent = entry[2];
    info.append(title, detail);
    const badge = document.createElement("span");
    badge.className = `status ${index < currentIndex ? "success" : index === currentIndex && active ? "running" : "neutral"}`;
    badge.textContent = index < currentIndex ? "Готово" : index === currentIndex && active ? "Выполняется" : "Ожидает";
    item.append(marker, info, badge);
    stages.append(item);
  });
}

async function loadActiveJob() {
  try {
    const resp = await apiFetch("/jobs/active");
    const data = await safeJson(resp);
    state.activeJob = data && data.job_id ? data : null;
  } catch (err) {
    state.activeJob = null;
    if (state.activeSection === "operations") showMessage(err.message || "Не удалось получить активную задачу.", "error");
  }
  renderActiveBanner();
  renderOperation(state.activeJob);
  renderMeetings();
}

async function cancelActiveJob() {
  const job = state.activeJob;
  if (!job || !job.job_id || !job.meeting_id) return;
  state.csrf = state.csrf || await getCsrfToken();
  if (!state.csrf) {
    showMessage("Нужно войти в систему перед отменой обработки.", "error");
    return;
  }
  try {
    await apiFetch(`/meetings/${encodeURIComponent(job.meeting_id)}/jobs/${encodeURIComponent(job.job_id)}/cancel`, { method: "POST", headers: { "X-CSRF-Token": state.csrf } });
    showMessage("Запрошена штатная остановка задачи.", "ok");
    await loadActiveJob();
  } catch (err) {
    showMessage(err.message || "Не удалось остановить задачу.", "error");
  }
}

function resetFilters() {
  byId("meetingSearch").value = "";
  byId("meetingStatusFilter").value = "";
  byId("meetingPeriodFilter").value = "all";
  renderMeetings();
}

function resetUpload() {
  byId("uploadForm").reset();
  byId("meetingFileName").textContent = "Файл не выбран";
  byId("postUploadAction").value = "full";
  byId("uploadResult").replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = "Здесь появится созданная карточка встречи.";
  byId("uploadResult").append(empty);
}

function wireEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => setSection(button.dataset.section || "meetings")));
  document.querySelectorAll("[data-create-mode]").forEach((button) => button.addEventListener("click", () => createMode(button.dataset.createMode || "upload")));
  document.querySelectorAll('input[name="profile-choice"]').forEach((input) => input.addEventListener("change", syncSelectedProfile));
  byId("showUploadBtn").addEventListener("click", () => { setSection("new-meeting"); createMode("upload"); });
  byId("showLiveBtn").addEventListener("click", () => { setSection("new-meeting"); createMode("live"); });
  byId("refreshMeetingsBtn").addEventListener("click", () => Promise.all([loadMeetings(), loadActiveJob()]));
  byId("refreshOperationsBtn").addEventListener("click", loadActiveJob);
  byId("activeWorkOpen").addEventListener("click", () => setSection("operations"));
  byId("operationCancel").addEventListener("click", cancelActiveJob);
  byId("loginSubmit").addEventListener("click", doLogin);
  byId("uploadForm").addEventListener("submit", uploadMeeting);
  byId("liveMeetingForm").addEventListener("submit", createLiveMeeting);
  byId("resetUploadBtn").addEventListener("click", resetUpload);
  byId("resetLiveMeetingBtn").addEventListener("click", () => { byId("liveMeetingForm").reset(); byId("liveMeetingDate").value = new Date().toISOString().slice(0, 10); });
  byId("meetingFile").addEventListener("change", () => { const file = byId("meetingFile").files[0]; byId("meetingFileName").textContent = file ? file.name : "Файл не выбран"; });
  ["meetingSearch", "meetingStatusFilter", "meetingPeriodFilter"].forEach((id) => byId(id).addEventListener(id === "meetingSearch" ? "input" : "change", renderMeetings));
  byId("resetFiltersBtn").addEventListener("click", resetFilters);
  byId("mobileMenu").addEventListener("click", () => byId("productNav").classList.toggle("open"));
  window.addEventListener("popstate", () => {
    const path = window.location.pathname;
    const section = path.endsWith("/new") ? "new-meeting" : path.endsWith("/processing") ? "operations" : "meetings";
    setSection(section, false);
  });
}

async function boot() {
  wireEvents();
  const today = new Date().toISOString().slice(0, 10);
  byId("meetingDate").value = today;
  byId("liveMeetingDate").value = today;
  createMode("upload");
  setSection(document.body.dataset.initialSection || "meetings", false);
  await refreshAuth();
  await Promise.all([loadMeetings(), loadActiveJob()]);
}

boot();
