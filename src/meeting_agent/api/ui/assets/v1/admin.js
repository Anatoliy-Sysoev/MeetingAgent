(() => {
  "use strict";

  const PAGE_SIZE = 25;
  const state = {
    offset: 0,
    total: 0,
    users: [],
    csrf: null,
    statusAction: null
  };

  function byId(id) {
    return document.getElementById(id);
  }

  async function safeJson(response) {
    try {
      return await response.json();
    } catch (_) {
      return null;
    }
  }

  function errorMessage(response, data) {
    if (response.status === 401) return "Сессия завершена. Войдите снова через MeetingAgent.";
    if (response.status === 403) return "У текущего пользователя нет прав администратора.";
    if (response.status === 409) return "Операция отклонена защитой последнего активного администратора.";
    if (response.status === 429) return "Слишком много запросов. Повторите позже.";
    if (data && typeof data.detail === "string") return data.detail.slice(0, 240);
    return `Ошибка HTTP ${response.status}`;
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = response.status === 204 ? null : await safeJson(response);
    if (!response.ok) throw new Error(errorMessage(response, data));
    return data;
  }

  function showMessage(text, kind) {
    const node = byId("page-message");
    node.textContent = text || "";
    node.className = "message";
    if (kind) node.classList.add(kind);
    node.hidden = !text;
  }

  function setFormError(id, text) {
    byId(id).textContent = text || "";
  }

  async function csrfToken() {
    if (state.csrf) return state.csrf;
    const data = await requestJson("/auth/csrf");
    if (!data || typeof data.csrf_token !== "string") {
      throw new Error("Не удалось получить CSRF-токен текущей сессии.");
    }
    state.csrf = data.csrf_token;
    return state.csrf;
  }

  async function writeJson(url, method, body) {
    const csrf = await csrfToken();
    const options = {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf
      }
    };
    if (body !== undefined) options.body = JSON.stringify(body);
    return requestJson(url, options);
  }

  function formatDate(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "—";
    return parsed.toLocaleString("ru-RU", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }

  function badge(text, className) {
    const node = document.createElement("span");
    node.className = className;
    node.textContent = text;
    return node;
  }

  async function loadSession() {
    const me = await requestJson("/auth/me");
    const label = me.display_name || me.email || "administrator";
    byId("session-user").textContent = label;
  }

  function renderSecurity(data) {
    byId("security-mode").textContent = data.deployment_mode || "unknown";
    byId("security-errors").textContent = String(Number(data.error_count) || 0);
    byId("security-warnings").textContent = String(Number(data.warning_count) || 0);

    const bootstrap = data.bootstrap_policy || {};
    let bootstrapLabel = bootstrap.first_admin_created ? "завершён" : "ожидает";
    if (bootstrap.remote_allowed) bootstrapLabel += ", remote";
    else bootstrapLabel += ", local-only";
    byId("security-bootstrap").textContent = bootstrapLabel;

    const proxy = data.trusted_proxy_policy || {};
    byId("security-proxy").textContent = proxy.configured
      ? `настроен (${Number(proxy.count) || 0})`
      : "не настроен";

    const body = byId("security-findings");
    body.replaceChildren();
    const findings = Array.isArray(data.findings) ? data.findings : [];
    byId("security-empty").hidden = findings.length !== 0;
    for (const finding of findings) {
      const row = document.createElement("tr");
      const severityCell = document.createElement("td");
      const severity = ["info", "warning", "error"].includes(finding.severity)
        ? finding.severity
        : "info";
      severityCell.append(badge(severity, `severity ${severity}`));
      const codeCell = document.createElement("td");
      codeCell.textContent = typeof finding.code === "string" ? finding.code : "configuration";
      const messageCell = document.createElement("td");
      messageCell.textContent = typeof finding.message === "string"
        ? finding.message.slice(0, 500)
        : "Проверка конфигурации завершена.";
      row.append(severityCell, codeCell, messageCell);
      body.append(row);
    }
  }

  async function loadSecurity() {
    const data = await requestJson("/admin/security/status");
    renderSecurity(data || {});
  }

  function rolesForUser(user) {
    return Array.isArray(user.roles) ? user.roles.filter((role) => typeof role === "string") : [];
  }

  function openEdit(user) {
    byId("edit-user-id").value = user.user_id || "";
    byId("edit-user-email").textContent = user.email || "";
    byId("edit-display-name").value = user.display_name || "";
    const selected = new Set(rolesForUser(user));
    for (const input of document.querySelectorAll('input[name="edit-role"]')) {
      input.checked = selected.has(input.value);
    }
    setFormError("edit-user-error", "");
    byId("edit-user-dialog").showModal();
  }

  function openStatus(user) {
    const enable = user.status !== "active";
    state.statusAction = { userId: user.user_id, enable };
    const actionText = enable ? "включить" : "отключить";
    byId("status-dialog-title").textContent = enable ? "Включить пользователя" : "Отключить пользователя";
    byId("status-dialog-detail").textContent = `Подтвердите: ${actionText} ${user.email || user.user_id}.`;
    const confirm = byId("status-confirm-btn");
    confirm.textContent = enable ? "Включить" : "Отключить";
    confirm.className = enable ? "primary" : "danger";
    setFormError("status-dialog-error", "");
    byId("status-dialog").showModal();
  }

  function renderUsers(data) {
    state.users = Array.isArray(data.users) ? data.users : [];
    state.total = Math.max(0, Number(data.total) || 0);
    state.offset = Math.max(0, Number(data.offset) || 0);
    const body = byId("users-body");
    body.replaceChildren();

    for (const user of state.users) {
      const row = document.createElement("tr");
      const identity = document.createElement("td");
      const name = document.createElement("div");
      name.className = "user-name";
      name.textContent = user.display_name || user.email || "Пользователь";
      const email = document.createElement("div");
      email.className = "user-email";
      email.textContent = user.email || "";
      identity.append(name, email);

      const rolesCell = document.createElement("td");
      const roles = document.createElement("div");
      roles.className = "roles";
      for (const role of rolesForUser(user)) roles.append(badge(role, "role"));
      if (!roles.childNodes.length) roles.append(badge("без роли", "role"));
      rolesCell.append(roles);

      const statusCell = document.createElement("td");
      const status = user.status === "active" ? "active" : "disabled";
      statusCell.append(badge(status, `status ${status}`));

      const lastLogin = document.createElement("td");
      lastLogin.className = "date-cell";
      lastLogin.textContent = formatDate(user.last_login_at);
      const updated = document.createElement("td");
      updated.className = "date-cell";
      updated.textContent = formatDate(user.updated_at);

      const actionsCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Изменить";
      edit.addEventListener("click", () => openEdit(user));
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.textContent = status === "active" ? "Отключить" : "Включить";
      if (status === "active") toggle.classList.add("danger-outline");
      toggle.addEventListener("click", () => openStatus(user));
      actions.append(edit, toggle);
      actionsCell.append(actions);
      row.append(identity, rolesCell, statusCell, lastLogin, updated, actionsCell);
      body.append(row);
    }

    byId("users-empty").hidden = state.users.length !== 0;
    byId("users-total").textContent = `${state.total} пользователей`;
    const pageNumber = Math.floor(state.offset / PAGE_SIZE) + 1;
    const pageCount = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
    byId("users-page").textContent = `Страница ${pageNumber} из ${pageCount}`;
    byId("users-prev").disabled = state.offset === 0;
    byId("users-next").disabled = state.offset + PAGE_SIZE >= state.total;
  }

  async function loadUsers() {
    const params = new URLSearchParams({
      offset: String(state.offset),
      limit: String(PAGE_SIZE)
    });
    const data = await requestJson(`/admin/users?${params.toString()}`);
    renderUsers(data || {});
  }

  function selectedRoles(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`))
      .map((input) => input.value);
  }

  async function createUser(event) {
    event.preventDefault();
    setFormError("create-user-error", "");
    try {
      await writeJson("/admin/users", "POST", {
        email: byId("create-email").value.trim(),
        display_name: byId("create-display-name").value.trim() || null,
        password: byId("create-password").value,
        roles: selectedRoles("create-role")
      });
      byId("create-user-dialog").close();
      byId("create-user-form").reset();
      const viewer = document.querySelector('input[name="create-role"][value="viewer"]');
      if (viewer) viewer.checked = true;
      state.offset = 0;
      await loadUsers();
      showMessage("Пользователь создан.", "ok");
    } catch (error) {
      setFormError("create-user-error", error.message);
    }
  }

  async function editUser(event) {
    event.preventDefault();
    setFormError("edit-user-error", "");
    const userId = byId("edit-user-id").value;
    try {
      await writeJson(`/admin/users/${encodeURIComponent(userId)}`, "PATCH", {
        display_name: byId("edit-display-name").value.trim() || null,
        roles: selectedRoles("edit-role")
      });
      byId("edit-user-dialog").close();
      await loadUsers();
      showMessage("Параметры пользователя обновлены.", "ok");
    } catch (error) {
      setFormError("edit-user-error", error.message);
    }
  }

  async function changeStatus() {
    const action = state.statusAction;
    if (!action) return;
    setFormError("status-dialog-error", "");
    const endpoint = action.enable ? "enable" : "disable";
    try {
      await writeJson(`/admin/users/${encodeURIComponent(action.userId)}/${endpoint}`, "POST");
      byId("status-dialog").close();
      state.statusAction = null;
      await loadUsers();
      showMessage(action.enable ? "Пользователь включён." : "Пользователь отключён.", "ok");
    } catch (error) {
      setFormError("status-dialog-error", error.message);
    }
  }

  async function logout() {
    try {
      const csrf = await csrfToken();
      await requestJson("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf }
      });
      window.location.assign("/MeetingAgent");
    } catch (error) {
      showMessage(error.message, "error");
    }
  }

  async function refreshAll() {
    showMessage("", "");
    try {
      await Promise.all([loadSession(), loadSecurity(), loadUsers()]);
    } catch (error) {
      showMessage(error.message, "error");
    }
  }

  function bindEvents() {
    byId("refresh-btn").addEventListener("click", refreshAll);
    byId("logout-btn").addEventListener("click", logout);
    byId("create-user-btn").addEventListener("click", () => {
      setFormError("create-user-error", "");
      byId("create-user-dialog").showModal();
    });
    byId("create-user-form").addEventListener("submit", createUser);
    byId("edit-user-form").addEventListener("submit", editUser);
    byId("status-confirm-btn").addEventListener("click", changeStatus);
    byId("users-prev").addEventListener("click", async () => {
      state.offset = Math.max(0, state.offset - PAGE_SIZE);
      await loadUsers().catch((error) => showMessage(error.message, "error"));
    });
    byId("users-next").addEventListener("click", async () => {
      if (state.offset + PAGE_SIZE < state.total) state.offset += PAGE_SIZE;
      await loadUsers().catch((error) => showMessage(error.message, "error"));
    });
    for (const button of document.querySelectorAll("[data-close-dialog]")) {
      button.addEventListener("click", () => byId(button.dataset.closeDialog).close());
    }
  }

  bindEvents();
  refreshAll();
})();
