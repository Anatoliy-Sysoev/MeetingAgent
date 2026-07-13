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
      if (data && data.detail && typeof data.detail.message === "string") {
        return data.detail.message.slice(0, 240);
      }
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
      if (item.source_kind === "live_session") return "live MIC/SYS";
      if (Number(item.media_count) > 0) return "загруженная запись";
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
        title.className = "meeting-title";
        const id = document.createElement("div");
        id.textContent = item.meeting_id || "";
        id.className = "mono meeting-id";
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
      title.className = "meeting-title";
      title.textContent = data.title || data.meeting_id;
      const id = document.createElement("div");
      id.className = "mono";
      id.textContent = data.meeting_id;
      const actions = document.createElement("div");
      actions.className = "actions upload-actions";
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
      const date = byId("liveMeetingDate").value;
      const body = {
        title,
        language: byId("liveMeetingLanguage").value || "ru"
      };
      if (date) body.date = date;
      const submit = byId("liveMeetingSubmit");
      submit.disabled = true;
      showMessage("Создаю live-встречу...", null);
      try {
        const resp = await apiFetch("/meetings/live", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": state.csrf
          },
          body: JSON.stringify(body)
        });
        const data = await safeJson(resp);
        const workspaceUrl = data && data.workspace_url;
        if (!workspaceUrl || !workspaceUrl.startsWith("/meetings/")) {
          throw new Error("Сервер не вернул адрес Workspace.");
        }
        showMessage("Live-встреча создана. Открываю Workspace...", "ok");
        window.location.assign(workspaceUrl);
      } catch (err) {
        submit.disabled = false;
        showMessage(err.message || "Live-встреча не создана.", "error");
      }
    }

    function selectedAsrEngine() {
      const select = byId("asrEngine");
      return select ? select.value : "faster-whisper";
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
          body: JSON.stringify({ profile, asr_engine: selectedAsrEngine() })
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
      byId("showLiveBtn").addEventListener("click", () => {
        setSection("new-meeting");
        byId("liveMeetingTitle").focus();
      });
      byId("refreshMeetingsBtn").addEventListener("click", loadMeetings);
      byId("loginSubmit").addEventListener("click", doLogin);
      byId("uploadForm").addEventListener("submit", uploadMeeting);
      byId("liveMeetingForm").addEventListener("submit", createLiveMeeting);
      byId("resetUploadBtn").addEventListener("click", () => {
        byId("uploadForm").reset();
        byId("uploadResult").replaceChildren();
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Здесь появится созданная карточка встречи.";
        byId("uploadResult").append(empty);
      });
      byId("resetLiveMeetingBtn").addEventListener("click", () => {
        byId("liveMeetingForm").reset();
        byId("liveMeetingDate").value = new Date().toISOString().slice(0, 10);
      });
    }

    async function boot() {
      wireEvents();
      const today = new Date().toISOString().slice(0, 10);
      byId("meetingDate").value = today;
      byId("liveMeetingDate").value = today;
      await refreshAuth();
      await loadMeetings();
    }

    boot();
