from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["meetingagent-ui"])


MEETINGAGENT_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MeetingAgent</title>
  <style>
    :root {
      --bg: #eef2f6;
      --surface: #ffffff;
      --panel: #f8fafc;
      --line: #d8e0e8;
      --line-strong: #b9c5d1;
      --text: #1f2933;
      --muted: #667383;
      --primary: #168ccc;
      --primary-soft: #e7f5fd;
      --ok: #148f61;
      --warn: #b7791f;
      --danger: #c53030;
      --shadow: 0 12px 28px rgba(31, 41, 51, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    button, input, select { font: inherit; letter-spacing: 0; }
    button {
      border: 1px solid var(--line-strong);
      background: var(--surface);
      border-radius: 4px;
      padding: 7px 12px;
      cursor: pointer;
    }
    button:hover { border-color: var(--primary); background: var(--primary-soft); }
    button:disabled { cursor: not-allowed; opacity: 0.55; background: #f1f5f9; }
    button.primary {
      color: #ffffff;
      border-color: var(--primary);
      background: var(--primary);
    }
    button.primary:hover { background: #0f78b3; }
    input, select {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 4px;
      background: #ffffff;
      padding: 8px 10px;
      color: var(--text);
    }
    label {
      display: grid;
      gap: 5px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
      text-transform: uppercase;
    }
    a { color: var(--primary); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .shell {
      display: grid;
      grid-template-columns: 232px minmax(0, 1fr);
      min-height: 100vh;
    }
    .nav {
      background: #182433;
      color: #dce6f0;
      padding: 18px 14px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }
    .brand {
      display: grid;
      gap: 3px;
      padding: 4px 6px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.12);
    }
    .brand-title { font-size: 18px; font-weight: 700; color: #fff; }
    .brand-subtitle { font-size: 12px; color: #a8b7c7; }
    .nav-list { display: grid; gap: 6px; }
    .nav-item {
      border: 0;
      color: #dce6f0;
      background: transparent;
      text-align: left;
      padding: 9px 10px;
      border-radius: 4px;
    }
    .nav-item.active, .nav-item:hover {
      color: #ffffff;
      background: rgba(66, 174, 234, 0.18);
      text-decoration: none;
    }
    .nav-link {
      display: block;
      color: #dce6f0;
      padding: 9px 10px;
      border-radius: 4px;
    }
    .nav-link:hover {
      color: #ffffff;
      background: rgba(66, 174, 234, 0.18);
      text-decoration: none;
    }
    .main {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
    }
    .topbar {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      padding: 14px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .topbar h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
    }
    .topbar p { margin: 3px 0 0; color: var(--muted); }
    .auth {
      min-width: 260px;
      text-align: right;
      color: var(--muted);
      font-size: 12px;
    }
    .content {
      padding: 18px 22px 28px;
      display: grid;
      gap: 16px;
    }
    .banner {
      display: none;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--primary);
      background: var(--surface);
      border-radius: 4px;
      color: var(--text);
    }
    .banner.visible { display: block; }
    .banner.error { border-left-color: var(--danger); }
    .banner.ok { border-left-color: var(--ok); }
    .grid {
      display: grid;
      grid-template-columns: minmax(360px, 430px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel-header {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: #fbfcfd;
    }
    .panel-title { font-weight: 700; }
    .panel-note { color: var(--muted); font-size: 12px; }
    .panel-body { padding: 14px; }
    .form-grid { display: grid; gap: 12px; }
    .row { display: flex; gap: 8px; align-items: center; }
    .row > * { flex: 1; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 4px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      min-width: 760px;
    }
    th, td {
      padding: 10px 9px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      background: var(--panel);
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    tr:hover td { background: #f8fbfd; }
    .status {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      background: #e2e8f0;
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }
    .status.ready, .status.done, .status.analyzed, .status.indexed { background: #d1fae5; color: #065f46; }
    .status.failed { background: #fee2e2; color: #991b1b; }
    .status.processing, .status.transcribing { background: #fef3c7; color: #92400e; }
    .empty {
      padding: 24px;
      color: var(--muted);
      text-align: center;
    }
    .login-panel {
      display: none;
      grid-template-columns: 1fr 1fr auto;
      gap: 8px;
      align-items: end;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
    }
    .login-panel.visible { display: grid; }
    .mono { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      .nav { position: static; }
      .grid { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; }
      .auth { text-align: left; }
      .login-panel { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="nav">
      <div class="brand">
        <div class="brand-title">MeetingAgent</div>
        <div class="brand-subtitle">Встречи, транскрипты, протоколы</div>
      </div>
      <nav class="nav-list">
        <button class="nav-item active" type="button" data-section="meetings">Встречи</button>
        <button class="nav-item" type="button" data-section="new-meeting">Новая запись</button>
        <button class="nav-item" type="button" data-section="operations">Обработка</button>
        <a class="nav-link" href="/ui">Джун бот</a>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <h1 id="pageTitle">Встречи</h1>
          <p id="pageSubtitle">Реестр записей, статусы обработки и быстрый запуск pipeline.</p>
        </div>
        <div class="auth">
          <div id="authStatus">Проверка входа...</div>
          <div class="login-panel" id="loginPanel">
            <label>Email
              <input id="loginEmail" type="email" placeholder="admin@local" autocomplete="username" />
            </label>
            <label>Пароль
              <input id="loginPassword" type="password" placeholder="Пароль" autocomplete="current-password" />
            </label>
            <button id="loginSubmit" class="primary" type="button">Войти</button>
          </div>
        </div>
      </header>
      <div class="content">
        <div class="banner" id="message"></div>

        <section class="grid" id="section-meetings">
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Быстрые действия</div>
                <div class="panel-note">Основные сценарии без технических деталей.</div>
              </div>
            </div>
            <div class="panel-body">
              <div class="actions">
                <button class="primary" id="showUploadBtn" type="button">Загрузить запись</button>
                <button id="refreshMeetingsBtn" type="button">Обновить реестр</button>
                <a href="/ui"><button type="button">Открыть Джун бота</button></a>
              </div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Реестр встреч</div>
                <div class="panel-note" id="meetingsCount">Загрузка...</div>
              </div>
            </div>
            <div class="panel-body">
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Дата</th>
                      <th>Название</th>
                      <th>Статус</th>
                      <th>Источник</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody id="meetingsTable"></tbody>
                </table>
              </div>
              <div class="empty" id="meetingsEmpty">Встречи не загружены.</div>
            </div>
          </div>
        </section>

        <section class="grid" id="section-new-meeting" hidden>
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Новая запись</div>
                <div class="panel-note">Загрузка mp4/mp3/wav/m4a в локальную карточку встречи.</div>
              </div>
            </div>
            <div class="panel-body">
              <form class="form-grid" id="uploadForm">
                <label>Файл записи
                  <input id="meetingFile" name="file" type="file" accept=".mp4,.mp3,.wav,.m4a,.webm,.ogg" required />
                </label>
                <label>Название встречи
                  <input id="meetingTitle" name="title" type="text" placeholder="Например: Паспорт проекта" />
                </label>
                <label>Дата встречи
                  <input id="meetingDate" name="date" type="date" />
                </label>
                <label>Сценарий после загрузки
                  <select id="postUploadAction">
                    <option value="none">Только создать карточку</option>
                    <option value="transcript_only">Запустить транскрибацию</option>
                    <option value="full">Запустить полный pipeline</option>
                  </select>
                </label>
                <div class="panel-note">
                  Сейчас pipeline использует продуктовый ASR: faster-whisper large-v3-turbo.
                  GigaAM доступен в CLI/backend, но отдельный выбор движка в UI будет следующим шагом.
                </div>
                <div class="actions">
                  <button class="primary" id="uploadSubmit" type="submit">Загрузить</button>
                  <button id="resetUploadBtn" type="button">Очистить</button>
                </div>
              </form>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Результат загрузки</div>
                <div class="panel-note">После загрузки можно открыть workspace или запустить обработку.</div>
              </div>
            </div>
            <div class="panel-body" id="uploadResult">
              <div class="empty">Здесь появится созданная карточка встречи.</div>
            </div>
          </div>
        </section>

        <section class="grid" id="section-operations" hidden>
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Активная обработка</div>
                <div class="panel-note">Текущая задача pipeline/job runner.</div>
              </div>
            </div>
            <div class="panel-body" id="activeJobPanel">
              <div class="empty">Активная задача не найдена.</div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Как запускать</div>
                <div class="panel-note">Пользовательский поток обработки записи.</div>
              </div>
            </div>
            <div class="panel-body">
              <ol>
                <li>Откройте вкладку <b>Новая запись</b> и выберите видео или аудио.</li>
                <li>Выберите сценарий: только транскрипт или полный pipeline.</li>
                <li>После старта откройте карточку встречи и следите за стадиями.</li>
                <li>Готовые артефакты появятся в Workspace: транскрипт, спикеры, протокол, задачи, риски.</li>
              </ol>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    const state = {
      csrf: null,
      user: null,
      meetings: [],
      activeSection: "meetings"
    };

    const pageTitles = {
      "meetings": ["Встречи", "Реестр записей, статусы обработки и быстрый запуск pipeline."],
      "new-meeting": ["Новая запись", "Загрузите видео или аудио и запустите обработку."],
      "operations": ["Обработка", "Активные jobs и понятная последовательность pipeline."]
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
      if (resp.status === 401 || resp.status === 403) {
        return "Нужно войти в систему или у пользователя не хватает прав.";
      }
      if (resp.status === 409 && data && data.duplicate) {
        return "Такая запись уже загружена.";
      }
      if (data && typeof data.detail === "string") return data.detail;
      if (data && data.detail && data.detail.error) return data.detail.error;
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

    async function refreshAuth() {
      const status = byId("authStatus");
      const loginPanel = byId("loginPanel");
      const resp = await fetch("/auth/me");
      if (!resp.ok) {
        state.user = null;
        status.textContent = "Вход не выполнен";
        loginPanel.classList.add("visible");
        return;
      }
      const data = await safeJson(resp);
      state.user = data;
      const roles = data && data.roles ? data.roles.join(", ") : "user";
      status.textContent = `вы вошли: ${data.email} (${roles})`;
      loginPanel.classList.remove("visible");
    }

    async function doLogin() {
      const email = byId("loginEmail").value.trim();
      const password = byId("loginPassword").value;
      const resp = await fetch("/auth/local/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      if (!resp.ok) {
        showMessage("Войти не удалось. Проверьте логин и пароль.", "error");
        return;
      }
      state.csrf = null;
      await refreshAuth();
      await loadMeetings();
      showMessage("Вход выполнен.", "ok");
    }

    function setSection(section) {
      state.activeSection = section;
      for (const el of document.querySelectorAll("[id^='section-']")) {
        el.hidden = el.id !== `section-${section}`;
      }
      for (const btn of document.querySelectorAll(".nav-item")) {
        btn.classList.toggle("active", btn.dataset.section === section);
      }
      const title = pageTitles[section] || pageTitles.meetings;
      byId("pageTitle").textContent = title[0];
      byId("pageSubtitle").textContent = title[1];
      if (section === "operations") {
        loadActiveJob();
      }
    }

    function meetingSourceName(item) {
      const source = item.source || {};
      const files = source.media_files || [];
      if (files.length > 0) return files[0].original_filename || files[0].path || "media";
      return "нет файла";
    }

    function meetingStatus(item) {
      return item.processing_status || item.status || "unknown";
    }

    function renderMeetings(items) {
      const tbody = byId("meetingsTable");
      const empty = byId("meetingsEmpty");
      const count = byId("meetingsCount");
      tbody.replaceChildren();
      count.textContent = `${items.length} встреч`;
      empty.hidden = items.length > 0;

      for (const item of items) {
        const tr = document.createElement("tr");
        const dateTd = document.createElement("td");
        dateTd.textContent = item.date || "";

        const titleTd = document.createElement("td");
        const title = document.createElement("div");
        title.textContent = item.title || item.meeting_id;
        title.style.fontWeight = "700";
        const id = document.createElement("div");
        id.textContent = item.meeting_id || "";
        id.className = "mono";
        id.style.color = "var(--muted)";
        titleTd.append(title, id);

        const statusTd = document.createElement("td");
        const badge = document.createElement("span");
        const status = meetingStatus(item);
        badge.textContent = status;
        badge.className = `status ${status}`;
        statusTd.append(badge);

        const sourceTd = document.createElement("td");
        sourceTd.textContent = meetingSourceName(item);

        const actionsTd = document.createElement("td");
        const actions = document.createElement("div");
        actions.className = "actions";
        const open = document.createElement("a");
        open.href = `/meetings/${encodeURIComponent(item.meeting_id)}/workspace`;
        open.textContent = "Открыть";
        const transcript = document.createElement("button");
        transcript.type = "button";
        transcript.textContent = "Транскрибировать";
        transcript.dataset.meetingId = item.meeting_id;
        transcript.addEventListener("click", () => startPipeline(item.meeting_id, "transcript_only"));
        const full = document.createElement("button");
        full.type = "button";
        full.textContent = "Полный pipeline";
        full.dataset.meetingId = item.meeting_id;
        full.addEventListener("click", () => startPipeline(item.meeting_id, "full"));
        actions.append(open, transcript, full);
        actionsTd.append(actions);

        tr.append(dateTd, titleTd, statusTd, sourceTd, actionsTd);
        tbody.append(tr);
      }
    }

    async function loadMeetings() {
      try {
        const resp = await apiFetch("/meetings?limit=200");
        const data = await safeJson(resp);
        const items = data.items || data.meetings || [];
        state.meetings = items;
        renderMeetings(items);
      } catch (err) {
        renderMeetings([]);
        showMessage(err.message || "Не удалось загрузить встречи.", "error");
      }
    }

    function renderUploadResult(data) {
      const panel = byId("uploadResult");
      panel.replaceChildren();
      const title = document.createElement("div");
      title.style.fontWeight = "700";
      title.textContent = data.title || data.meeting_id;
      const id = document.createElement("div");
      id.className = "mono";
      id.textContent = data.meeting_id;
      const actions = document.createElement("div");
      actions.className = "actions";
      actions.style.marginTop = "12px";
      const open = document.createElement("a");
      open.href = `/meetings/${encodeURIComponent(data.meeting_id)}/workspace`;
      open.textContent = "Открыть workspace";
      const transcript = document.createElement("button");
      transcript.type = "button";
      transcript.textContent = "Запустить транскрибацию";
      transcript.addEventListener("click", () => startPipeline(data.meeting_id, "transcript_only"));
      const full = document.createElement("button");
      full.type = "button";
      full.textContent = "Запустить полный pipeline";
      full.addEventListener("click", () => startPipeline(data.meeting_id, "full"));
      actions.append(open, transcript, full);
      panel.append(title, id, actions);
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
      if (!fd.get("title")) fd.delete("title");
      if (!fd.get("date")) fd.delete("date");
      const submit = byId("uploadSubmit");
      submit.disabled = true;
      showMessage("Загружаю запись...", null);
      try {
        const resp = await apiFetch("/meetings/ingest", {
          method: "POST",
          headers: { "X-CSRF-Token": state.csrf },
          body: fd
        });
        const data = await safeJson(resp);
        renderUploadResult(data);
        await loadMeetings();
        showMessage("Запись загружена и карточка встречи создана.", "ok");
        const action = byId("postUploadAction").value;
        if (action !== "none") {
          await startPipeline(data.meeting_id, action);
        }
      } catch (err) {
        showMessage(err.message || "Загрузка не выполнена.", "error");
      } finally {
        submit.disabled = false;
      }
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
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": state.csrf
          },
          body: JSON.stringify({ profile })
        });
        const data = await safeJson(resp);
        showMessage(`Pipeline запущен: ${data.job_id || data.pipeline_id || profile}`, "ok");
        setSection("operations");
        await loadActiveJob();
      } catch (err) {
        showMessage(err.message || "Pipeline не запущен.", "error");
      }
    }

    async function loadActiveJob() {
      const panel = byId("activeJobPanel");
      try {
        const resp = await apiFetch("/jobs/active");
        const data = await safeJson(resp);
        panel.replaceChildren();
        if (!data || !data.job_id) {
          const empty = document.createElement("div");
          empty.className = "empty";
          empty.textContent = "Активная задача не найдена.";
          panel.append(empty);
          return;
        }
        const rows = [
          ["Job", data.job_id],
          ["Встреча", data.meeting_id],
          ["Тип", data.kind || "stage"],
          ["Стадия", data.stage || data.current_stage || ""],
          ["Статус", data.status || ""]
        ];
        for (const row of rows) {
          const line = document.createElement("div");
          line.className = "row";
          const key = document.createElement("b");
          key.textContent = row[0];
          const value = document.createElement("span");
          value.textContent = row[1] || "-";
          line.append(key, value);
          panel.append(line);
        }
      } catch (err) {
        panel.replaceChildren();
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = err.message || "Не удалось получить активную задачу.";
        panel.append(empty);
      }
    }

    function wireEvents() {
      for (const btn of document.querySelectorAll(".nav-item")) {
        btn.addEventListener("click", () => setSection(btn.dataset.section || "meetings"));
      }
      byId("showUploadBtn").addEventListener("click", () => setSection("new-meeting"));
      byId("refreshMeetingsBtn").addEventListener("click", loadMeetings);
      byId("loginSubmit").addEventListener("click", doLogin);
      byId("uploadForm").addEventListener("submit", uploadMeeting);
      byId("resetUploadBtn").addEventListener("click", () => {
        byId("uploadForm").reset();
        byId("uploadResult").replaceChildren();
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Здесь появится созданная карточка встречи.";
        byId("uploadResult").append(empty);
      });
    }

    async function boot() {
      wireEvents();
      const today = new Date().toISOString().slice(0, 10);
      byId("meetingDate").value = today;
      await refreshAuth();
      await loadMeetings();
    }

    boot();
  </script>
</body>
</html>
"""


@router.get("/MeetingAgent", response_class=HTMLResponse)
async def meetingagent_home() -> HTMLResponse:
    return HTMLResponse(MEETINGAGENT_HTML)
