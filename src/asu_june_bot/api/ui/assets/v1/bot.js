const maxChars = Number(document.body.dataset.maxQueryChars || "0");

    const hints = {
      mode: {
        hybrid: 'Ищет и по смыслу, и по точным совпадениям. Обычно лучший вариант.',
        vector: 'Подходит для свободных формулировок, когда точные слова неизвестны.',
        bm25: 'Полезно для номеров ФТТ, ПМИ, разделов, аббревиатур и точных терминов.'
      },
      model: {
        'qwen3.5:4b': 'Единый режим для проектного чата и проверок качества.'
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
    const runtimeWarning = document.getElementById('runtimeWarning');
    const answerStatus = document.getElementById('answerStatus');
    const sourceCount = document.getElementById('sourceCount');
    const sources = document.getElementById('sources');
    const sourcesSummary = document.getElementById('sourcesSummary');
    const diagnostics = document.getElementById('diagnostics');
    const diagnosticsSummary = document.getElementById('diagnosticsSummary');
    const authStatus = document.getElementById('authStatus');
    const adminNav = document.getElementById('adminNav');
    const authPanel = document.getElementById('authPanel');
    const loginEmail = document.getElementById('loginEmail');
    const loginPassword = document.getElementById('loginPassword');
    const loginSubmit = document.getElementById('loginSubmit');
    const loginError = document.getElementById('loginError');

    // --------------- Auth ---------------
    async function safeJson(resp) {
      try { return await resp.json(); } catch (_) { return null; }
    }

    async function getCsrfToken() {
      try {
        const resp = await fetch('/auth/csrf');
        if (!resp.ok) return null;
        const data = await resp.json();
        return data.csrf_token || null;
      } catch (_) { return null; }
    }

    async function refreshAuthState() {
      try {
        const resp = await fetch('/auth/me');
        if (resp.ok) {
          const me = await resp.json();
          const who = me.email || me.principal_id || 'пользователь';
          const roles = Array.isArray(me.roles) && me.roles.length ? ` (${me.roles.join(', ')})` : '';
          authStatus.textContent = `вы вошли: ${who}${roles}`;
          authStatus.className = 'badge ok';
          const permissions = Array.isArray(me.permissions) ? me.permissions : [];
          adminNav.hidden = !permissions.includes('users.manage');
          authPanel.hidden = true;
          return true;
        }
      } catch (_) { /* fallthrough */ }
      authStatus.textContent = 'вход не выполнен';
      authStatus.className = 'badge error';
      adminNav.hidden = true;
      authPanel.hidden = false;
      return false;
    }

    async function doLogin() {
      loginError.textContent = '';
      const email = loginEmail.value.trim();
      const password = loginPassword.value;
      if (!email || !password) {
        loginError.textContent = 'Укажите email и пароль.';
        return;
      }
      loginSubmit.disabled = true;
      try {
        const resp = await fetch('/auth/local/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        if (resp.ok) {
          loginPassword.value = '';
          await refreshAuthState();
        } else if (resp.status === 429) {
          loginError.textContent = 'Слишком много попыток входа. Попробуйте позже.';
        } else {
          loginError.textContent = 'Неверный email или пароль.';
        }
      } catch (_) {
        loginError.textContent = 'Не удалось выполнить вход. Проверьте, что API запущен.';
      } finally {
        loginSubmit.disabled = false;
      }
    }

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
      sources.replaceChildren();
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
      runtimeWarning.textContent = '';
      runtimeWarning.classList.remove('active');
      answer.textContent = '';
      const pending = document.createElement('div');
      pending.className = 'empty-state';
      pending.textContent = 'Идёт поиск источников...';
      sources.replaceChildren(pending);
      diagnostics.textContent = '{}';
      diagnosticsSummary.textContent = 'ожидание ответа';
    }

    function renderError(message) {
      topStatus.textContent = 'Ошибка';
      answerStatus.className = 'badge error';
      answerStatus.textContent = 'ошибка';
      runtimeWarning.textContent = '';
      runtimeWarning.classList.remove('active');
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
        const csrf = await getCsrfToken();
        const headers = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;
        const response = await fetch('/chat', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            query: text,
            mode: document.getElementById('mode').value,
            top_k: Number(document.getElementById('topK').value || 8),
            model: document.getElementById('model').value || null,
            max_tokens: 1400,
            timeout_sec: 300,
            include_diagnostics: includeDiagnostics
          })
        });
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            renderError('Нет доступа: войдите в систему, чтобы задавать вопросы.');
            await refreshAuthState();
            return;
          }
          if (response.status === 429) {
            renderError('Слишком много запросов. Подождите немного и повторите.');
            return;
          }
          const errBody = await safeJson(response);
          renderError(`HTTP ${response.status}\n${errBody ? JSON.stringify(errBody, null, 2) : 'ответ без деталей'}`);
          return;
        }
        const data = await safeJson(response);
        if (!data) {
          renderError('Сервер вернул некорректный ответ. Повторите запрос.');
          return;
        }

        const status = data.status || 'unknown';
        topStatus.textContent = `Статус: ${status}`;
        answerStatus.textContent = status;
        answerStatus.className = status === 'answered' ? 'badge ok' : (status === 'truncated' ? 'badge warning' : 'badge error');
        const semanticWarnings = data?.warnings?.semantic?.items || data?.diagnostics?.semantic_warnings?.items || [];
        const truncated = status === 'truncated' || data?.diagnostics?.llm_finish_reason === 'length' || semanticWarnings.some((item) => item.code === 'truncated_answer');
        if (truncated) {
          runtimeWarning.textContent = 'Ответ обрезан лимитом генерации, нужно повторить с большим лимитом.';
          runtimeWarning.classList.add('active');
        } else {
          runtimeWarning.textContent = '';
          runtimeWarning.classList.remove('active');
        }
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
        renderError(`Ошибка запроса. Проверьте, что API запущен.\n${String(error)}`);
      } finally {
        send.disabled = false;
      }
    }

    // --------------- Review tab ---------------
    const REVIEW_LABELS = ['correct','false_refuse','false_clarify','bad_source','needs_case','off_topic_ok','needs_review'];

    async function getReviewCsrfToken() {
      return getCsrfToken();
    }

    async function loadReviewRuns() {
      const statusEl = document.getElementById('reviewStatus');
      const listEl = document.getElementById('reviewList');
      statusEl.textContent = 'Загрузка...';
      listEl.replaceChildren();
      const status = document.getElementById('reviewFilterStatus').value;
      const guard = document.getElementById('reviewFilterGuard').value;
      const label = document.getElementById('reviewFilterLabel').value;
      const params = new URLSearchParams({ limit: 100 });
      if (status) params.set('status', status);
      if (guard) params.set('guard_decision', guard);
      if (label) params.set('label', label);
      try {
        const resp = await fetch('/admin/review/chat-runs?' + params.toString());
        if (resp.status === 401 || resp.status === 403) {
          statusEl.textContent = `Ошибка ${resp.status}: недостаточно прав (требуется admin с review.manage).`;
          return;
        }
        if (!resp.ok) {
          statusEl.textContent = `Ошибка ${resp.status}`;
          return;
        }
        const data = await resp.json();
        const items = data.items || [];
        statusEl.textContent = `Загружено: ${items.length} runs`;
        renderReviewList(items);
      } catch (e) {
        statusEl.textContent = 'Ошибка запроса: ' + String(e);
      }
    }

    function addMetaSpan(parent, value, className) {
      const span = document.createElement('span');
      if (className) span.className = className;
      span.textContent = value || '';
      parent.appendChild(span);
    }

    function renderReviewList(items) {
      const listEl = document.getElementById('reviewList');
      listEl.replaceChildren();
      if (!items.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'Нет runs по заданным фильтрам.';
        listEl.appendChild(empty);
        return;
      }
      for (const run of items) {
        const card = document.createElement('div');
        card.className = 'review-card';
        const meta = document.createElement('div');
        meta.className = 'review-card-meta';
        addMetaSpan(meta, run.run_id);
        addMetaSpan(meta, run.created_at || '');
        addMetaSpan(meta, run.status || '', 'badge');
        addMetaSpan(meta, run.guard_decision || '', 'badge');
        if (run.current_label) {
          addMetaSpan(meta, run.current_label, 'badge ok');
        }
        const query = document.createElement('div');
        query.className = 'review-card-query';
        query.textContent = run.query || '';
        const preview = document.createElement('div');
        preview.className = 'review-card-preview';
        preview.textContent = (run.answer_preview || '').slice(0, 200);
        const labelRow = document.createElement('div');
        labelRow.className = 'review-label-row';
        const sel = document.createElement('select');
        sel.className = 'review-label-select';
        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = '— выбрать label —';
        sel.appendChild(defaultOpt);
        for (const l of REVIEW_LABELS) {
          const opt = document.createElement('option');
          opt.value = l;
          opt.textContent = l;
          if (run.current_label === l) opt.selected = true;
          sel.appendChild(opt);
        }
        const issueInput = document.createElement('input');
        issueInput.type = 'text';
        issueInput.placeholder = 'manual_issue (опционально)';
        issueInput.className = 'review-issue-input';
        issueInput.value = run.manual_issue || '';
        const commentInput = document.createElement('input');
        commentInput.type = 'text';
        commentInput.placeholder = 'comment (опционально)';
        commentInput.className = 'review-comment-input';
        commentInput.value = run.comment || '';
        const btn = document.createElement('button');
        btn.className = 'small-action';
        btn.textContent = 'Сохранить';
        btn.addEventListener('click', async () => {
          const lbl = sel.value;
          if (!lbl) { alert('Выберите label'); return; }
          btn.disabled = true;
          try {
            const csrf = await getReviewCsrfToken();
            const headers = {'Content-Type':'application/json'};
            if (csrf) headers['X-CSRF-Token'] = csrf;
            const r = await fetch('/admin/review/chat-runs/' + encodeURIComponent(run.run_id) + '/label', {
              method: 'POST',
              headers,
              body: JSON.stringify({
                label: lbl,
                manual_issue: issueInput.value || null,
                comment: commentInput.value || null
              })
            });
            if (r.ok) {
              const existing = meta.querySelector('.badge.ok');
              if (existing) existing.remove();
              addMetaSpan(meta, lbl, 'badge ok');
            } else {
              const err = await r.json().catch(() => ({}));
              alert('Ошибка ' + r.status + ': ' + JSON.stringify(err.detail || err));
            }
          } finally {
            btn.disabled = false;
          }
        });
        labelRow.appendChild(sel);
        labelRow.appendChild(issueInput);
        labelRow.appendChild(commentInput);
        labelRow.appendChild(btn);
        card.appendChild(meta);
        card.appendChild(query);
        card.appendChild(preview);
        card.appendChild(labelRow);
        listEl.appendChild(card);
      }
    }

    document.getElementById('reviewLoad').addEventListener('click', loadReviewRuns);
    // ------------------------------------------

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
    loginSubmit.addEventListener('click', doLogin);
    loginPassword.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') doLogin();
    });
    refreshAuthState();

    updateCounter();
    updateHints();
