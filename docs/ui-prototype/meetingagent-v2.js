(function () {
  "use strict";

  const screenTitles = {
    registry: ["Встречи", "MeetingAgent / Встречи"],
    create: ["Новая встреча", "MeetingAgent / Новая встреча"],
    processing: ["Обработка", "MeetingAgent / Обработка"],
    workspace: ["Карточка встречи", "MeetingAgent / Встречи / Карточка"],
  };
  const roleLabels = {
    viewer: "Наблюдатель",
    editor: "Редактор",
    admin: "Администратор",
  };
  const roleRank = { viewer: 1, editor: 2, admin: 3 };

  function queryValue(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function setScreen(next) {
    const screen = Object.hasOwn(screenTitles, next) ? next : "registry";
    document.querySelectorAll("[data-screen]").forEach((node) => {
      node.hidden = node.dataset.screen !== screen;
    });
    document.querySelectorAll("[data-screen-link]").forEach((node) => {
      const active = node.dataset.screenLink === screen;
      node.classList.toggle("active", active);
      if (node.matches(".primary-nav button")) {
        node.setAttribute("aria-current", active ? "page" : "false");
      }
    });
    document.getElementById("page-title").textContent = screenTitles[screen][0];
    document.getElementById("breadcrumbs").textContent = screenTitles[screen][1];
    document.body.dataset.activeScreen = screen;
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function setCreateMode(next) {
    const mode = next === "live" ? "live" : "upload";
    document.querySelectorAll("[data-create-mode]").forEach((node) => {
      node.classList.toggle("active", node.dataset.createMode === mode);
    });
    document.querySelectorAll("[data-create-panel]").forEach((node) => {
      node.hidden = node.dataset.createPanel !== mode;
    });
  }

  function setRole(next) {
    const role = Object.hasOwn(roleRank, next) ? next : "editor";
    document.getElementById("prototype-role").value = role;
    document.getElementById("role-badge").textContent = roleLabels[role];
    document.querySelectorAll("[data-min-role]").forEach((node) => {
      node.hidden = roleRank[role] < roleRank[node.dataset.minRole];
    });
  }

  document.querySelectorAll("[data-screen-link]").forEach((node) => {
    node.addEventListener("click", (event) => {
      if (node.tagName !== "A") {
        event.preventDefault();
      }
      setScreen(node.dataset.screenLink);
    });
  });
  document.querySelectorAll("[data-create-mode]").forEach((node) => {
    node.addEventListener("click", () => setCreateMode(node.dataset.createMode));
  });
  document.getElementById("prototype-role").addEventListener("change", (event) => {
    setRole(event.target.value);
  });
  document.getElementById("mobile-menu").addEventListener("click", () => {
    document.querySelector(".rail").classList.toggle("open");
  });
  document.querySelector(".primary-nav").addEventListener("keydown", (event) => {
    if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const items = Array.from(document.querySelectorAll(".primary-nav button"));
    const current = items.indexOf(document.activeElement);
    const direction = event.key === 'ArrowDown' ? 1 : -1;
    items[(current + direction + items.length) % items.length].focus();
    event.preventDefault();
  });

  setScreen(queryValue("screen") || window.location.hash.slice(1));
  setCreateMode(queryValue("mode"));
  setRole(queryValue("role"));
}());
