// fő alkalmazás JS – külön fájl
import {
  uid, clamp, fmtDateTime, parseLocalDateTime,
  setSecondAlignedInterval, humanRemaining, toHex,
  parseICS
} from './vz-utils.js';

(() => {
  const { READ_ONLY, INITIAL_DATA, API_BASE } = window.__VZ__ || {};
  if (!INITIAL_DATA) {
    console.error('Hiányzó INITIAL_DATA');
    return;
  }

  // ----- Állapot -----
  const state = {
    counters: INITIAL_DATA.counters || [],
    projects: INITIAL_DATA.projects || [],
    showArchived: false,
    sortMode: 'manual',
    selectedProjects: new Set(), // üres = minden látszik
    calendars: []
  };

  // ----- API -----
  async function apiGet(path) {
    const r = await fetch(`${API_BASE}/${path}`);
    if (!r.ok) throw new Error(`GET ${path} ${r.status}`);
    return r.json();
  }
  async function apiSend(method, path, body) {
    const r = await fetch(`${API_BASE}/${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
    if (!r.ok) throw new Error(`${method} ${path} ${r.status}`);
    return r.json();
  }
  const api = {
    createProject: (p) => apiSend('POST', 'project', p),
    updateProject: (id, patch) => apiSend('PUT', `project/${id}`, patch),
    deleteProject: (id) => apiSend('DELETE', `project/${id}`),
    createCounter: (c) => apiSend('POST', 'counter', c),
    updateCounter: (id, patch) => apiSend('PUT', `counter/${id}`, patch),
    deleteCounter: (id) => apiSend('DELETE', `counter/${id}`),
  };

  // ----- DOM elemek -----
  const sidebar = document.getElementById('sidebar');
  const listEl = document.getElementById('list');
  const emptyEl = document.getElementById('emptyState');
  const emptyHintAdmin = document.getElementById('emptyHintAdmin');
  const activeCountEl = document.getElementById('activeCount');
  const sortSel = document.getElementById('sortMode');
  const showArchivedChk = document.getElementById('showArchived');
  const projectsPanel = document.getElementById('projectsPanel');
  const modeBadge = document.getElementById('modeBadge');

  const projectFilterBox = document.getElementById('projectFilterBox');
  const btnToggleAllFilters = document.getElementById('btnToggleAllFilters');

  // Dialog elemek
  const counterDialog = document.getElementById('counterDialog');
  const counterForm = document.getElementById('counterForm');
  const counterId = document.getElementById('counterId');
  const counterName = document.getElementById('counterName');
  const counterWhen = document.getElementById('counterWhen');
  const counterProject = document.getElementById('counterProject');
  const btnDeleteCounter = document.getElementById('btnDeleteCounter');
  const btnQuickNewProject = document.getElementById('btnQuickNewProject');

  const projectDialog = document.getElementById('projectDialog');
  const projectForm = document.getElementById('projectForm');
  const projectIdEl = document.getElementById('projectId');
  const projectNameEl = document.getElementById('projectName');
  const projectColorEl = document.getElementById('projectColor');
  const projectFontEl = document.getElementById('projectFont');
  const btnDeleteProject = document.getElementById('btnDeleteProject');

  // ICS
  const icsInput = document.getElementById('icsInput');
  const icsUrlInput = document.getElementById('icsUrl');
  const btnIcsFromUrl = document.getElementById('btnIcsFromUrl');
  const calendarList = document.getElementById('calendarList');

  // ----- Init -----
  (function init() {
    if (READ_ONLY) {
      sidebar.classList.add('hidden');
      modeBadge.textContent = 'Publikus nézet';
      document.getElementById('btnNewCounter').disabled = true;
      document.getElementById('btnNewProject').disabled = true;
      if (icsInput) icsInput.disabled = true;
      if (icsUrlInput) icsUrlInput.disabled = true;
      if (btnIcsFromUrl) btnIcsFromUrl.disabled = true;
      emptyHintAdmin.style.display = 'none';
    } else {
      modeBadge.textContent = 'Admin';
    }

    // Általános gombok
    const closeBtns = document.querySelectorAll('dialog [data-close]');
    closeBtns.forEach(b => b.addEventListener('click', (e) => e.target.closest('dialog').close()));

    // Oldalsáv események
    document.getElementById('btnNewCounter').addEventListener('click', () => {
      if (READ_ONLY) return;
      if (!state.projects.length) state.projects.push({ id: uid('prj'), name: 'Alap', color: '#6ea8fe', font: 'default' });
      openCounterDialog();
    });
    document.getElementById('btnNewProject').addEventListener('click', () => !READ_ONLY && openProjectDialog());

    sortSel.addEventListener('change', () => { state.sortMode = sortSel.value; renderAll(); });
    showArchivedChk.addEventListener('change', () => { state.showArchived = showArchivedChk.checked; renderAll(); });

    // ICS fájl
    if (icsInput) {
      icsInput.addEventListener('change', async (e) => {
        if (READ_ONLY) return;
        const files = Array.from(e.target.files || []);
        for (const f of files) {
          const text = await f.text();
          const cal = parseICS(text);
          cal.id = uid('cal');
          cal.name = f.name;
          state.calendars.push(cal);
        }
        renderCalendars();
      });
    }
    // ICS url
    if (btnIcsFromUrl) {
      btnIcsFromUrl.addEventListener('click', async () => {
        if (READ_ONLY) return;
        const url = (icsUrlInput?.value || '').trim();
        if (!url) { alert('Adj meg egy .ics URL-t.'); return; }
        try {
          btnIcsFromUrl.disabled = true;
          btnIcsFromUrl.textContent = 'Betöltés...';
          const r = await fetch(`/visszaszamlalo/api/ics_proxy?url=${encodeURIComponent(url)}`);
          if (!r.ok) throw new Error(await r.text());
          const text = await r.text();
          const cal = parseICS(text);
          cal.id = uid('cal');
          cal.name = url.split('/').pop() || 'calendar.ics';
          state.calendars.push(cal);
          renderCalendars();
        } catch (e) {
          alert('Nem sikerült betölteni az ICS-t: ' + e.message);
        } finally {
          btnIcsFromUrl.disabled = false;
          btnIcsFromUrl.textContent = 'Betöltés URL-ről';
        }
      });
    }

    // Dialog események
    counterForm.addEventListener('submit', onCounterSubmit);
    btnDeleteCounter.addEventListener('click', onCounterDelete);
    btnQuickNewProject.addEventListener('click', () => openProjectDialog());

    projectForm.addEventListener('submit', onProjectSubmit);
    btnDeleteProject.addEventListener('click', onProjectDelete);

    // Kezdeti render + másodperc-igazított frissítés
    renderAll();
    setSecondAlignedInterval(tick);

    // Gyorsgomb adminnak
    window.addEventListener('keydown', (e) => {
      if (!READ_ONLY && e.key === 'n' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault(); document.getElementById('btnNewCounter').click();
      }
    });
  })();

  // ----- Render -----
  function renderAll() {
    sortSel.value = state.sortMode;
    showArchivedChk.checked = state.showArchived;
    renderProjectsPanel();
    renderProjectFilterBox();
    renderList();
  }

  function getProject(id) { return state.projects.find(p => p.id === id); }
  function getProjectName(c) { return (getProject(c.projectId)?.name) || ''; }

  function visibleCounters() {
    const useAll = state.selectedProjects.size === 0;
    return state.counters.filter(c => {
      if (!state.showArchived && c.archived) return false;
      if (useAll) return true;
      return state.selectedProjects.has(c.projectId || null);
    });
  }

  function sortCounters(arr) {
    const mode = state.sortMode;
    if (mode === 'manual') return arr.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    if (mode === 'project') return arr.sort((a, b) => (getProjectName(a).localeCompare(getProjectName(b)) || (a.deadline - b.deadline)));
    if (mode === 'asc') return arr.sort((a, b) => a.deadline - b.deadline);
    if (mode === 'desc') return arr.sort((a, b) => b.deadline - a.deadline);
    return arr;
  }

  function renderList() {
    listEl.innerHTML = '';
    const items = sortCounters(visibleCounters().slice());

    activeCountEl.textContent = state.counters.filter(c => !c.archived).length;
    emptyEl.style.display = items.length ? 'block' : 'none'; // később átállítjuk
    if (items.length) emptyEl.style.display = 'none';

    items.forEach((c) => {
      const p = getProject(c.projectId) || { name: '(nincs projekt)', color: '#888', font: 'default' };
      const card = document.createElement('div');
      card.className = 'card' + (c.archived ? ' archived' : '');
      card.setAttribute('data-id', c.id);
      card.setAttribute('data-deadline', c.deadline);
      card.setAttribute('data-created', c.createdAt || Date.now());
      card.draggable = (!READ_ONLY && state.sortMode === 'manual');

      const drag = document.createElement('div'); drag.className = 'drag'; drag.innerHTML = '☰';

      const center = document.createElement('div');
      const right = document.createElement('div'); right.className = 'actions';

      const title = document.createElement('div'); title.className = 'title'; title.textContent = c.name;
      if (!READ_ONLY) {
        title.style.cursor = 'pointer';
        title.title = 'Kattintás: szerkesztés';
        title.addEventListener('click', () => openCounterDialog(c));
      }

      const meta = document.createElement('div'); meta.className = 'meta';
      const tag = document.getElementById('tplProjectChip').content.firstElementChild.cloneNode(true);
      tag.querySelector('.name').textContent = p.name;
      tag.querySelector('.project-dot').style.background = p.color;
      tag.setAttribute('data-project-font', p.font || 'default');

      const when = document.createElement('span'); when.className = 'pill when'; when.textContent = new Date(c.deadline).toLocaleString();
      const until = document.createElement('span'); until.className = 'pill until';
      meta.append(tag, when, until);

      const barWrap = document.createElement('div');
      barWrap.style.height = '4px'; barWrap.style.background = 'rgba(255,255,255,.08)';
      barWrap.style.border = '1px solid var(--border)'; barWrap.style.borderRadius = '999px';
      barWrap.style.overflow = 'hidden'; barWrap.title = 'Becsült előrehaladás';
      const bar = document.createElement('div'); bar.className = 'bar'; bar.style.height = '100%'; bar.style.width = '0%'; bar.style.background = p.color; barWrap.append(bar);

      center.append(title, meta, barWrap);

      if (!READ_ONLY) {
        const btnEdit = document.createElement('button'); btnEdit.className = 'btn secondary'; btnEdit.textContent = 'Szerk.'; btnEdit.onclick = () => openCounterDialog(c);
        const btnArchive = document.createElement('button'); btnArchive.className = 'btn secondary'; btnArchive.textContent = c.archived ? 'Visszaállít' : 'Archiválás';
        btnArchive.onclick = async () => {
          try { await api.updateCounter(c.id, { archived: !c.archived }); c.archived = !c.archived; renderAll(); }
          catch (e) { alert('Nem sikerült menteni: ' + e.message); }
        };
        right.append(btnEdit, btnArchive);
      }

      card.append(drag, center, right);

      if (!READ_ONLY && state.sortMode === 'manual') {
        card.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', c.id); e.dataTransfer.effectAllowed = 'move'; });
        card.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
        card.addEventListener('drop', async (e) => {
          e.preventDefault();
          const fromId = e.dataTransfer.getData('text/plain');
          const toId = c.id;
          await reorder(fromId, toId);
        });
      }

      listEl.append(card);
    });

    tick();
  }

  async function reorder(fromId, toId) {
    if (fromId === toId) return;
    const arr = sortCounters(visibleCounters().slice());
    const fromIdx = arr.findIndex(x => x.id === fromId);
    const toIdx = arr.findIndex(x => x.id === toId);
    if (fromIdx < 0 || toIdx < 0) return;
    const [moved] = arr.splice(fromIdx, 1);
    arr.splice(toIdx, 0, moved);
    for (let i = 0; i < arr.length; i++) {
      const real = state.counters.find(x => x.id === arr[i].id);
      if (real) {
        real.order = i;
        if (!READ_ONLY) {
          try { await api.updateCounter(real.id, { order: real.order }); } catch { /* noop */ }
        }
      }
    }
    renderList();
  }

  function renderProjectsPanel() {
    projectsPanel.innerHTML = '';
    if (!state.projects.length) {
      const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = READ_ONLY ? '—' : 'Nincs projekt. Hozz létre egyet!';
      projectsPanel.append(empty); return;
    }
    state.projects.forEach(p => {
      const row = document.createElement('div'); row.className = 'row'; row.style.justifyContent = 'space-between';
      const left = document.createElement('div'); left.className = 'row'; left.style.gap = '8px';
      const dot = document.createElement('span'); dot.className = 'project-dot'; dot.style.background = p.color;
      const name = document.createElement('span'); name.textContent = p.name; name.setAttribute('data-project-font', p.font || 'default');
      left.append(dot, name);
      row.append(left);

      if (!READ_ONLY) {
        const right = document.createElement('div');
        const b = document.createElement('button'); b.className = 'btn secondary'; b.textContent = 'Szerk.'; b.onclick = () => openProjectDialog(p);
        right.append(b); row.append(right);
      }
      projectsPanel.append(row);
    });
  }

  function renderProjectFilterBox() {
    projectFilterBox.innerHTML = '';
    state.projects.forEach(p => {
      const id = `pf_${p.id}`;
      const row = document.createElement('label');
      row.className = 'row';
      row.style.gap = '8px';
      row.style.cursor = 'pointer';

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = id;
      cb.checked = state.selectedProjects.has(p.id);
      cb.addEventListener('change', () => {
        if (cb.checked) state.selectedProjects.add(p.id);
        else state.selectedProjects.delete(p.id);
        renderList();
      });

      const dot = document.createElement('span'); dot.className = 'project-dot'; dot.style.background = p.color;
      const name = document.createElement('span'); name.textContent = p.name; name.setAttribute('data-project-font', p.font || 'default');
      row.append(cb, dot, name);
      projectFilterBox.append(row);
    });

    if (btnToggleAllFilters) {
      btnToggleAllFilters.onclick = () => {
        const total = state.projects.length;
        const selected = state.selectedProjects.size;
        const selectAll = selected < total;
        state.selectedProjects = new Set(selectAll ? state.projects.map(p => p.id) : []);
        renderProjectFilterBox();
        renderList();
      };
    }
  }

  // ----- Tick (másodperchez igazítva) -----
  function tick() {
    document.querySelectorAll('[data-deadline]').forEach(el => {
      const ms = Number(el.getAttribute('data-deadline')) - Date.now();
      const untilEl = el.querySelector('.until');
      if (untilEl) untilEl.textContent = humanRemaining(ms);
      const bar = el.querySelector('.bar');
      if (bar) {
        const created = Number(el.getAttribute('data-created')) || Date.now();
        const total = Number(el.getAttribute('data-deadline')) - created;
        const passed = Date.now() - created;
        const pct = total > 0 ? clamp(Math.round(passed / total * 100), 0, 100) : 100;
        bar.style.width = pct + '%';
      }
    });
  }

  // ----- Számláló dialog -----
  function fillProjectSelect(sel) {
    sel.innerHTML = '';
    state.projects.forEach(p => {
      const o = document.createElement('option'); o.value = p.id; o.textContent = p.name; sel.appendChild(o);
    });
  }

  function openCounterDialog(counter) {
    if (READ_ONLY) return;
    document.getElementById('dlgTitle').textContent = counter ? 'Számláló szerkesztése' : 'Új számláló';
    fillProjectSelect(counterProject);
    btnDeleteCounter.style.display = counter ? 'inline-flex' : 'none';

    if (counter) {
      counterId.value = counter.id;
      counterName.value = counter.name;
      counterWhen.value = new Date(counter.deadline).toISOString().slice(0, 16);
      counterProject.value = counter.projectId || (state.projects[0]?.id || '');
    } else {
      counterId.value = '';
      counterName.value = '';
      counterWhen.value = new Date(Date.now() + 3600_000).toISOString().slice(0, 16);
      counterProject.value = state.projects[0]?.id || '';
    }
    counterDialog.showModal();
  }

  async function onCounterSubmit(e) {
    e.preventDefault();
    if (READ_ONLY) return;
    const id = counterId.value || uid('ctr');
    const existing = state.counters.find(x => x.id === id);
    const data = {
      id,
      name: counterName.value.trim(),
      deadline: parseLocalDateTime(counterWhen.value),
      projectId: counterProject.value || null,
      archived: existing ? existing.archived : false,
      createdAt: existing ? existing.createdAt : Date.now(),
      order: existing ? existing.order : (state.counters.length ? Math.max(...state.counters.map(x => x.order || 0)) + 1 : 0)
    };
    try {
      if (!existing) { await api.createCounter(data); state.counters.push(data); }
      else { await api.updateCounter(id, data); Object.assign(existing, data); }
      counterDialog.close(); renderAll();
    } catch (err) { alert('Mentési hiba: ' + err.message); }
  }

  async function onCounterDelete() {
    if (READ_ONLY) return;
    const id = counterId.value; if (!id) return;
    try {
      await api.deleteCounter(id);
      const i = state.counters.findIndex(c => c.id === id); if (i >= 0) state.counters.splice(i, 1);
      counterDialog.close(); renderAll();
    } catch (e) { alert('Törlési hiba: ' + e.message); }
  }

  // ----- Projekt dialog -----
  function openProjectDialog(project) {
    if (READ_ONLY) return;
    document.getElementById('projDlgTitle').textContent = project ? 'Projekt szerkesztése' : 'Új projekt';
    btnDeleteProject.style.display = project ? 'inline-flex' : 'none';
    if (project) {
      projectIdEl.value = project.id;
      projectNameEl.value = project.name;
      projectColorEl.value = toHex(project.color || '#6ea8fe');
      projectFontEl.value = project.font || 'default';
    } else {
      projectIdEl.value = ''; projectNameEl.value = ''; projectColorEl.value = '#6ea8fe'; projectFontEl.value = 'default';
    }
    projectDialog.showModal();
  }

  async function onProjectSubmit(e) {
    e.preventDefault();
    if (READ_ONLY) return;
    const id = projectIdEl.value || uid('prj');
    const existing = state.projects.find(x => x.id === id);
    const data = { id, name: projectNameEl.value.trim(), color: projectColorEl.value, font: projectFontEl.value };
    try {
      if (!existing) { await api.createProject(data); state.projects.push(data); }
      else { await api.updateProject(id, data); Object.assign(existing, data); }
      projectDialog.close();
      if (counterDialog.open) fillProjectSelect(counterProject);
      renderAll();
    } catch (err) { alert('Projekt mentési hiba: ' + err.message); }
  }

  async function onProjectDelete() {
    if (READ_ONLY) return;
    const id = projectIdEl.value; if (!id) return;
    try {
      await api.deleteProject(id);
      state.counters.forEach(c => { if (c.projectId === id) c.projectId = null; });
      const i = state.projects.findIndex(p => p.id === id); if (i >= 0) state.projects.splice(i, 1);
      projectDialog.close(); renderAll();
    } catch (e) { alert('Projekt törlési hiba: ' + e.message); }
  }

  // ----- ICS lista -----
  function renderCalendars() {
    calendarList.innerHTML = '';
    if (!state.calendars.length) {
      const x = document.createElement('div'); x.className = 'cal-item'; x.textContent = 'Még nincs betöltött naptár.'; calendarList.append(x); return;
    }
    state.calendars.forEach(cal => {
      const wrap = document.createElement('details');
      wrap.className = 'cal-item';
      const sum = document.createElement('summary'); sum.textContent = `${cal.name} — ${cal.events.length} esemény`;
      wrap.append(sum);
      cal.events.slice(0, 500).forEach(ev => {
        const row = document.createElement('div'); row.className = 'event'; row.title = READ_ONLY ? '' : 'Dupla katt: előtöltés új számlálóhoz';
        const left = document.createElement('div'); left.textContent = ev.summary || '(nincs cím)';
        const right = document.createElement('div'); right.className = 'when'; right.textContent = new Date(ev.dtstart).toLocaleString();
        row.append(left, right);
        if (!READ_ONLY) {
          row.addEventListener('dblclick', () => {
            if (!state.projects.length) state.projects.push({ id: uid('prj'), name: 'Alap', color: '#6ea8fe', font: 'default' });
            openCounterDialog();
            counterName.value = ev.summary || '';
            counterWhen.value = new Date(ev.dtstart).toISOString().slice(0, 16);
          });
        }
        wrap.append(row);
      });
      calendarList.append(wrap);
    });
  }
})();
