from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from asu_june_bot.core.limits import MAX_QUERY_CHARS


router = APIRouter(tags=["ui"])


HTML = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Project Knowledge Bot</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0f172a;
      --panel: #111827;
      --border: #334155;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #60a5fa;
      --danger: #f87171;
      --ok: #34d399;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .page {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    textarea {{
      width: 100%;
      min-height: 130px;
      resize: vertical;
      border-radius: 10px;
      border: 1px solid var(--border);
      padding: 12px;
      background: #020617;
      color: var(--text);
      font-size: 15px;
      line-height: 1.45;
    }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 12px; }}
    label {{ font-size: 13px; color: var(--muted); }}
    select, input {{
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #020617;
      color: var(--text);
      padding: 8px;
    }}
    button {{
      border: 0;
      border-radius: 10px;
      padding: 10px 16px;
      background: var(--accent);
      color: #06111f;
      font-weight: 700;
      cursor: pointer;
    }}
    button:disabled {{ opacity: 0.55; cursor: not-allowed; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #020617;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      min-height: 120px;
      line-height: 1.45;
    }}
    .sources {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .source {{ border: 1px solid var(--border); border-radius: 10px; padding: 10px; background: #020617; }}
    .source-title {{ font-weight: 700; color: var(--text); margin-bottom: 4px; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); font-size: 12px; }}
    .error {{ color: var(--danger); }}
    .ok {{ color: var(--ok); }}
    .counter {{ min-width: 130px; text-align: right; }}
  </style>
</head>
<body>
  <main class="page">
    <section class="header">
      <div>
        <h1>Project Knowledge Bot</h1>
        <div class="muted">Локальный чат по проектной базе знаний. Ответы строятся только по источникам.</div>
      </div>
      <div class="badge">max query: {MAX_QUERY_CHARS}</div>
    </section>

    <section class="panel">
      <textarea id="query" maxlength="{MAX_QUERY_CHARS}" placeholder="Введите вопрос по документации..."></textarea>
      <div class="row">
        <label>Режим
          <select id="mode">
            <option value="hybrid" selected>hybrid</option>
            <option value="vector">vector</option>
            <option value="bm25">bm25</option>
          </select>
        </label>
        <label>top_k
          <input id="topK" type="number" min="1" max="50" value="5" />
        </label>
        <label>model
          <input id="model" type="text" value="qwen2.5:7b-instruct" />
        </label>
        <label>max_tokens
          <input id="maxTokens" type="number" min="1" max="4096" value="700" />
        </label>
        <button id="send">Спросить</button>
        <div id="counter" class="muted counter">0 / {MAX_QUERY_CHARS}</div>
      </div>
      <div id="status" class="muted" style="margin-top:10px;"></div>
    </section>

    <section class="panel">
      <div class="muted">Ответ</div>
      <pre id="answer">Нет ответа.</pre>
    </section>

    <section class="panel">
      <div class="muted" style="margin-bottom:10px;">Источники</div>
      <div id="sources" class="sources"></div>
    </section>

    <section class="panel">
      <div class="muted">Диагностика</div>
      <pre id="diagnostics">{{}}</pre>
    </section>
  </main>

  <script>
    const maxChars = {MAX_QUERY_CHARS};
    const query = document.getElementById('query');
    const counter = document.getElementById('counter');
    const send = document.getElementById('send');
    const statusBox = document.getElementById('status');
    const answer = document.getElementById('answer');
    const sources = document.getElementById('sources');
    const diagnostics = document.getElementById('diagnostics');

    function updateCounter() {{
      const length = query.value.length;
      counter.textContent = `${{length}} / ${{maxChars}}`;
      counter.className = length > maxChars * 0.9 ? 'counter error' : 'muted counter';
    }}

    function renderSources(items) {{
      sources.innerHTML = '';
      if (!items || !items.length) {{
        sources.innerHTML = '<div class="muted">Источники не возвращены.</div>';
        return;
      }}
      for (const item of items) {{
        const div = document.createElement('div');
        div.className = 'source';
        const title = item.title || item.path || item.source_ref || 'Источник';
        div.innerHTML = `
          <div class="source-title">${{item.source_ref || ''}} — ${{escapeHtml(title)}}</div>
          <div class="muted">section: ${{escapeHtml(item.section || '-')}}</div>
          <div class="muted">score: ${{item.score ?? '-'}}</div>
          <div style="margin-top:8px;">${{escapeHtml(item.text_preview || '')}}</div>
        `;
        sources.appendChild(div);
      }}
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }}

    async function ask() {{
      const text = query.value.trim();
      if (!text) {{
        statusBox.innerHTML = '<span class="error">Введите вопрос.</span>';
        return;
      }}
      send.disabled = true;
      statusBox.textContent = 'Запрос выполняется...';
      answer.textContent = '';
      sources.innerHTML = '';
      diagnostics.textContent = '{{}}';
      try {{
        const response = await fetch('/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            query: text,
            mode: document.getElementById('mode').value,
            top_k: Number(document.getElementById('topK').value || 5),
            model: document.getElementById('model').value || null,
            max_tokens: Number(document.getElementById('maxTokens').value || 700),
            timeout_sec: 300,
            include_diagnostics: true
          }})
        }});
        const data = await response.json();
        if (!response.ok) {{
          statusBox.innerHTML = `<span class="error">HTTP ${{response.status}}</span>`;
          answer.textContent = JSON.stringify(data, null, 2);
          return;
        }}
        statusBox.innerHTML = `<span class="ok">status: ${{escapeHtml(data.status)}}</span>`;
        answer.textContent = data.answer || 'Ответ пустой.';
        renderSources(data.sources || []);
        diagnostics.textContent = JSON.stringify(data.diagnostics || {{}}, null, 2);
      }} catch (error) {{
        statusBox.innerHTML = '<span class="error">Ошибка запроса. Проверьте, что API запущен.</span>';
        answer.textContent = String(error);
      }} finally {{
        send.disabled = false;
      }}
    }}

    query.addEventListener('input', updateCounter);
    send.addEventListener('click', ask);
    query.addEventListener('keydown', (event) => {{
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') ask();
    }});
    updateCounter();
  </script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(HTML)


@router.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(HTML)
