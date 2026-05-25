from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from asu_june_bot.core.limits import MAX_QUERY_CHARS


router = APIRouter(tags=["ui"])


HTML_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>АСУ Джун бот</title>
  <style>
    :root {
      --app-bg: #f3f5f7;
      --surface: #ffffff;
      --surface-soft: #f7f8fa;
      --line: #dfe5eb;
      --line-strong: #cbd5df;
      --text: #1f2933;
      --muted: #6b7785;
      --muted-soft: #9aa6b2;
      --primary: #42aeea;
      --primary-strong: #168ccc;
      --primary-soft: #e7f5fd;
      --danger: #e85a70;
      --ok: #1f9d68;
      --rail: #f8fafc;
      --shadow: 0 16px 36px rgba(31, 41, 51, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--app-bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }

    button, input, select, textarea { font: inherit; letter-spacing: 0; }

    .app-shell {
      display: grid;
      grid-template-columns: 56px 292px minmax(0, 1fr);
      min-height: 100vh;
    }

    .rail {
      background: var(--rail);
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px 0;
      gap: 16px;
    }

    .rail-logo {
      width: 32px;
      height: 44px;
      border: 1px solid var(--line-strong);
      border-radius: 4px;
      display: grid;
      place-items: center;
      color: #17212b;
      font-weight: 700;
      line-height: 1;
      writing-mode: vertical-rl;
      transform: rotate(180deg);
      background: #fff;
    }

    .rail-btn {
      width: 36px;
      height: 36px;
      border: 0;
      border-left: 3px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      cursor: default;
    }

    .rail-btn.active {
      color: var(--primary-strong);
      border-left-color: var(--primary);
      background: var(--primary-soft);
    }

    .sidebar {
      background: var(--surface);
      border-right: 1px solid var(--line);
      padding: 18px 14px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .sidebar-title {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }

    .sidebar-title h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }

    .small-action {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface-soft);
      color: var(--muted);
      padding: 6px 8px;
      font-size: 12px;
    }

    .chat-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .chat-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-soft);
      padding: 11px 12px;
      display: grid;
      gap: 4px;
    }

    .chat-item.active {
      background: var(--primary-soft);
      border-color: #b9e3f9;
    }

    .chat-name {
      font-weight: 700;
      color: var(--text);
    }

    .chat-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .future-label {
      display: inline-flex;
      width: fit-content;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2f6;
      color: var(--muted);
      font-size: 11px;
    }

    .main {
      min-width: 0;
      display: flex;
      flex-direction: column;
    }

    .topbar {
      height: 58px;
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      gap: 16px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .brand h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
    }

    .brand-subtitle {
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }

    .status-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 12px;
      color: var(--muted);
      background: var(--surface-soft);
      white-space: nowrap;
      font-size: 12px;
    }

    .workspace {
      padding: 22px 24px 28px;
      display: grid;
      gap: 16px;
      max-width: 1220px;
      width: 100%;
    }

    .tabs {
      display: flex;
      gap: 8px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
    }

    .tab-btn {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--muted);
      border-radius: 7px;
      padding: 9px 14px;
      cursor: pointer;
      min-width: 112px;
    }

    .tab-btn.active {
      color: #fff;
      border-color: var(--primary);
      background: var(--primary);
    }

    .tab-panel { display: none; }
    .tab-panel.active { display: grid; gap: 16px; }

    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .question-panel {
      padding: 18px;
      display: grid;
      gap: 14px;
    }

    .field-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }

    .field-title {
      font-weight: 700;
      font-size: 15px;
    }

    .muted {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    textarea {
      width: 100%;
      min-height: 144px;
      resize: vertical;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 13px 14px;
      background: #fff;
      color: var(--text);
      line-height: 1.5;
      outline: none;
    }

    textarea:focus, select:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(66, 174, 234, 0.16);
    }

    .settings-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 10px;
    }

    .setting {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: var(--surface-soft);
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .setting label {
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
    }

    select {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 7px;
      background: #fff;
      color: var(--text);
      padding: 9px 10px;
      min-height: 38px;
    }

    .setting-hint {
      color: var(--muted);
      font-size: 12px;
      min-height: 34px;
      line-height: 1.35;
    }

    .action-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .primary-btn {
      border: 0;
      border-radius: 7px;
      padding: 11px 18px;
      min-width: 132px;
      background: var(--primary);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }

    .primary-btn:hover { background: var(--primary-strong); }
    .primary-btn:disabled { opacity: 0.55; cursor: wait; }

    .answer-panel {
      padding: 18px;
      display: grid;
      gap: 12px;
    }

    .answer-box {
      min-height: 180px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-soft);
      padding: 16px;
      white-space: pre-wrap;
      line-height: 1.55;
    }

    .result-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      background: var(--surface-soft);
      font-size: 12px;
    }

    .badge.ok { color: var(--ok); border-color: #cdeee0; background: #effaf5; }
    .badge.error { color: var(--danger); border-color: #ffd5dc; background: #fff3f5; }

    .sources-list {
      display: grid;
      gap: 10px;
    }

    .source-row {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px 14px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
    }

    .source-title {
      font-weight: 700;
      line-height: 1.35;
    }

    .source-preview {
      color: var(--muted);
      margin-top: 7px;
      line-height: 1.45;
    }

    .score {
      color: var(--primary-strong);
      font-weight: 700;
      white-space: nowrap;
    }

    .empty-state {
      border: 1px dashed var(--line-strong);
      border-radius: 8px;
      padding: 26px;
      color: var(--muted);
      text-align: center;
      background: var(--surface-soft);
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      background: #17212b;
      color: #edf2f7;
      border-radius: 8px;
      padding: 16px;
      min-height: 220px;
      overflow: auto;
    }

    @media (max-width: 980px) {
      .app-shell { grid-template-columns: 48px minmax(0, 1fr); }
      .sidebar { display: none; }
      .settings-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); }
    }

    @media (max-width: 640px) {
      .app-shell { grid-template-columns: 1fr; }
      .rail { display: none; }
      .topbar { height: auto; padding: 14px 16px; align-items: flex-start; }
      .workspace { padding: 16px; }
      .settings-grid { grid-template-columns: 1fr; }
      .tabs { overflow-x: auto; }
      .tab-btn { min-width: 104px; }
    }
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="rail" aria-label="Основная навигация">
      <div class="rail-logo">АСУ</div>
      <button class="rail-btn active" title="Чаты" aria-label="Чаты">Ч</button>
      <button class="rail-btn" title="Источники" aria-label="Источники">И</button>
      <button class="rail-btn" title="Настройки" aria-label="Настройки">Н</button>
    </aside>

    <aside class="sidebar">
      <div class="sidebar-title">
        <h2>Чаты</h2>
        <button class="small-action" type="button" disabled>Новый</button>
      </div>
      <div class="chat-list">
        <div class="chat-item active">
          <div class="chat-name">Проектные вопросы</div>
          <div class="chat-meta">Текущая сессия по базе АСУ</div>
        </div>
        <div class="chat-item">
          <div class="chat-name">Проверка ФТТ</div>
          <div class="chat-meta">Отдельный чат для требований</div>
          <span class="future-label">позже</span>
        </div>
        <div class="chat-item">
          <div class="chat-name">ПМИ и сценарии</div>
          <div class="chat-meta">Вопросы по испытаниям</div>
          <span class="future-label">позже</span>
        </div>
        <div class="chat-item">
          <div class="chat-name">Архитектура и ЦТА</div>
          <div class="chat-meta">Технические решения проекта</div>
          <span class="future-label">позже</span>
        </div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="brand">
          <div>
            <h1>АСУ Джун бот</h1>
            <div class="brand-subtitle">Локальный помощник по проектной базе знаний</div>
          </div>
        </div>
        <div class="status-pill" id="topStatus">Готов к вопросу</div>
      </header>

      <div class="workspace">
        <nav class="tabs" aria-label="Разделы результата">
          <button class="tab-btn active" type="button" data-tab="chat">Чат</button>
          <button class="tab-btn" type="button" data-tab="sources">Источники</button>
          <button class="tab-btn" type="button" data-tab="diagnostics">Диагностика</button>
        </nav>

        <section id="tab-chat" class="tab-panel active">
          <div class="panel question-panel">
            <div class="field-header">
              <div>
                <div class="field-title">Вопрос</div>
                <div class="muted">Задавайте вопросы только по материалам проекта АСУ.</div>
              </div>
              <div id="counter" class="badge">0 / __MAX_QUERY_CHARS__</div>
            </div>

            <textarea id="query" maxlength="__MAX_QUERY_CHARS__" placeholder="Например: какие требования ФТТ относятся к строительному контролю?"></textarea>

            <div class="settings-grid">
              <div class="setting">
                <label for="mode">Способ поиска</label>
                <select id="mode">
                  <option value="hybrid" selected>Сбалансированный</option>
                  <option value="vector">По смыслу вопроса</option>
                  <option value="bm25">По точным словам и номерам</option>
                </select>
                <div class="setting-hint" id="modeHint">Ищет и по смыслу, и по точным совпадениям. Обычно лучший вариант.</div>
              </div>

              <div class="setting">
                <label for="model">Модель ответа</label>
                <select id="model">
                  <option value="qwen2.5:7b-instruct" selected>Основная локальная модель</option>
                  <option value="qwen3:4b">Быстрая проверка границы</option>
                  <option value="qwen3:8b">Тяжёлая модель для сложного случая</option>
                </select>
                <div class="setting-hint" id="modelHint">Основной режим: стабильнее для проектных вопросов, но отвечает не мгновенно.</div>
              </div>

              <div class="setting">
                <label for="topK">Глубина поиска</label>
                <select id="topK">
                  <option value="5">Быстро</option>
                  <option value="8" selected>Стандартно</option>
                  <option value="10">Расширенно</option>
                </select>
                <div class="setting-hint" id="topKHint">Сколько фрагментов документов брать в работу. Стандартно достаточно для большинства вопросов.</div>
              </div>

              <div class="setting">
                <label for="diagnosticsMode">Подробности ответа</label>
                <select id="diagnosticsMode">
                  <option value="on" selected>Показать источники и диагностику</option>
                  <option value="off">Показать только ответ</option>
                </select>
                <div class="setting-hint" id="diagnosticsHint">Для проверки качества оставляйте включённым: будет видно, откуда взят ответ.</div>
              </div>
            </div>

            <div class="action-row">
              <div class="muted">Ctrl + Enter тоже отправляет вопрос.</div>
              <button id="send" class="primary-btn" type="button">Спросить</button>
            </div>
          </div>

          <div class="panel answer-panel">
            <div class="field-header">
              <div class="field-title">Ответ</div>
              <div class="result-meta">
                <span id="answerStatus" class="badge">нет запроса</span>
                <span id="sourceCount" class="badge">источники: 0</span>
              </div>
            </div>
            <div id="answer" class="answer-box">Здесь появится ответ по проектным источникам.</div>
          </div>
        </section>

        <section id="tab-sources" class="tab-panel">
          <div class="panel answer-panel">
            <div class="field-header">
              <div>
                <div class="field-title">Источники</div>
                <div class="muted">Фрагменты документов, на которые опирался ответ.</div>
              </div>
              <span id="sourcesSummary" class="badge">нет данных</span>
            </div>
            <div id="sources" class="sources-list">
              <div class="empty-state">Спросите что-нибудь в чате, чтобы увидеть найденные источники.</div>
            </div>
          </div>
        </section>

        <section id="tab-diagnostics" class="tab-panel">
          <div class="panel answer-panel">
            <div class="field-header">
              <div>
                <div class="field-title">Диагностика</div>
                <div class="muted">Технический след запроса для проверки качества поиска и ответа.</div>
              </div>
              <span id="diagnosticsSummary" class="badge">выключено до первого запроса</span>
            </div>
            <pre id="diagnostics">{}</pre>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script>
    const maxChars = __MAX_QUERY_CHARS__;

    const hints = {
      mode: {
        hybrid: 'Ищет и по смыслу, и по точным совпадениям. Обычно лучший вариант.',
        vector: 'Подходит для свободных формулировок, когда точные слова неизвестны.',
        bm25: 'Полезно для номеров ФТТ, ПМИ, разделов, аббревиатур и точных терминов.'
      },
      model: {
        'qwen2.5:7b-instruct': 'Основной режим: стабильнее для проектных вопросов, но отвечает не мгновенно.',
        'qwen3:4b': 'Быстрее, подходит для грубой проверки границ вопроса.',
        'qwen3:8b': 'Тяжелее и медленнее; включайте только для сложных формулировок.'
      },
      topK: {
        '5': 'Быстрый режим: меньше источников, выше риск пропустить редкий документ.',
        '8': 'Стандартный режим: баланс скорости и полноты.',
        '10': 'Расширенный режим: больше источников, полезно для сборных вопросов.'
      },
      diagnostics: {
        on: 'Для проверки качества оставляйте включённым: будет видно, откуда взят ответ.',
        off: 'Скрывает технические подробности, но источники ответа всё равно сохраняются в ответе API.'
      }
    };

    const query = document.getElementById('query');
    const counter = document.getElementById('counter');
    const send = document.getElementById('send');
    const topStatus = document.getElementById('topStatus');
    const answer = document.getElementById('answer');
    const answerStatus = document.getElementById('answerStatus');
    const sourceCount = document.getElementById('sourceCount');
    const sources = document.getElementById('sources');
    const sourcesSummary = document.getElementById('sourcesSummary');
    const diagnostics = document.getElementById('diagnostics');
    const diagnosticsSummary = document.getElementById('diagnosticsSummary');

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    function setText(id, value) {
      document.getElementById(id).textContent = value;
    }

    function updateCounter() {
      const length = query.value.length;
      counter.textContent = `${length} / ${maxChars}`;
      counter.className = length > maxChars * 0.9 ? 'badge error' : 'badge';
    }

    function updateHints() {
      setText('modeHint', hints.mode[document.getElementById('mode').value]);
      setText('modelHint', hints.model[document.getElementById('model').value]);
      setText('topKHint', hints.topK[document.getElementById('topK').value]);
      setText('diagnosticsHint', hints.diagnostics[document.getElementById('diagnosticsMode').value]);
    }

    function setTab(name) {
      for (const button of document.querySelectorAll('.tab-btn')) {
        button.classList.toggle('active', button.dataset.tab === name);
      }
      for (const panel of document.querySelectorAll('.tab-panel')) {
        panel.classList.toggle('active', panel.id === `tab-${name}`);
      }
    }

    function renderSources(items) {
      sources.innerHTML = '';
      const list = Array.isArray(items) ? items : [];
      sourceCount.textContent = `источники: ${list.length}`;
      sourcesSummary.textContent = list.length ? `${list.length} найдено` : 'нет источников';

      if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Источники не возвращены.';
        sources.appendChild(empty);
        return;
      }

      for (const item of list) {
        const row = document.createElement('article');
        row.className = 'source-row';

        const body = document.createElement('div');
        const title = item.source_url ? document.createElement('a') : document.createElement('div');
        title.className = 'source-title';
        title.textContent = item.title || item.path || item.relative_path || item.source_ref || 'Источник';
        if (item.source_url) {
          title.href = item.source_url;
          title.target = '_blank';
          title.rel = 'noopener noreferrer';
        }

        const meta = document.createElement('div');
        meta.className = 'muted';
        meta.textContent = [
          item.source_ref ? `ссылка: ${item.source_ref}` : '',
          item.source_url ? 'cloud' : '',
          item.section ? `раздел: ${item.section}` : '',
          item.chunk_index !== undefined ? `chunk: ${item.chunk_index}` : ''
        ].filter(Boolean).join(' • ');

        const preview = document.createElement('div');
        preview.className = 'source-preview';
        preview.textContent = item.text_preview || item.preview || '';

        body.appendChild(title);
        body.appendChild(meta);
        if (preview.textContent) body.appendChild(preview);

        const score = document.createElement('div');
        score.className = 'score';
        score.textContent = item.score !== undefined ? Number(item.score).toFixed(3) : '-';

        row.appendChild(body);
        row.appendChild(score);
        sources.appendChild(row);
      }
    }

    function resetBeforeRequest() {
      send.disabled = true;
      topStatus.textContent = 'Запрос выполняется...';
      answerStatus.className = 'badge';
      answerStatus.textContent = 'в работе';
      sourceCount.textContent = 'источники: 0';
      answer.textContent = '';
      sources.innerHTML = '<div class="empty-state">Идёт поиск источников...</div>';
      diagnostics.textContent = '{}';
      diagnosticsSummary.textContent = 'ожидание ответа';
    }

    function renderError(message) {
      topStatus.textContent = 'Ошибка';
      answerStatus.className = 'badge error';
      answerStatus.textContent = 'ошибка';
      answer.textContent = message;
      diagnostics.textContent = '{}';
      diagnosticsSummary.textContent = 'ошибка запроса';
    }

    async function ask() {
      const text = query.value.trim();
      if (!text) {
        renderError('Введите вопрос.');
        return;
      }

      resetBeforeRequest();
      const includeDiagnostics = document.getElementById('diagnosticsMode').value === 'on';

      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: text,
            mode: document.getElementById('mode').value,
            top_k: Number(document.getElementById('topK').value || 8),
            model: document.getElementById('model').value || null,
            max_tokens: 900,
            timeout_sec: 300,
            include_diagnostics: includeDiagnostics
          })
        });
        const data = await response.json();
        if (!response.ok) {
          renderError(`HTTP ${response.status}\\n${JSON.stringify(data, null, 2)}`);
          return;
        }

        const status = data.status || 'unknown';
        topStatus.textContent = `Статус: ${status}`;
        answerStatus.textContent = status;
        answerStatus.className = status === 'answered' ? 'badge ok' : 'badge error';
        answer.textContent = data.answer || 'Ответ пустой.';
        renderSources(data.sources || []);

        if (includeDiagnostics) {
          diagnostics.textContent = JSON.stringify(data.diagnostics || {}, null, 2);
          diagnosticsSummary.textContent = 'получена';
        } else {
          diagnostics.textContent = '{}';
          diagnosticsSummary.textContent = 'скрыта пользователем';
        }
      } catch (error) {
        renderError(`Ошибка запроса. Проверьте, что API запущен.\\n${String(error)}`);
      } finally {
        send.disabled = false;
      }
    }

    for (const button of document.querySelectorAll('.tab-btn')) {
      button.addEventListener('click', () => setTab(button.dataset.tab));
    }
    for (const id of ['mode', 'model', 'topK', 'diagnosticsMode']) {
      document.getElementById(id).addEventListener('change', updateHints);
    }
    query.addEventListener('input', updateCounter);
    query.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') ask();
    });
    send.addEventListener('click', ask);

    updateCounter();
    updateHints();
  </script>
</body>
</html>"""


HTML = HTML_TEMPLATE.replace("__MAX_QUERY_CHARS__", str(MAX_QUERY_CHARS))


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(HTML)


@router.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(HTML)
