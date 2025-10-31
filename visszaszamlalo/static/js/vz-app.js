// fő alkalmazás JS – modul
import {
  uid, clamp, fmtDateTime, parseLocalDateTime,
  setSecondAlignedInterval, humanRemaining, toHex,
  parseICS
} from './vz-utils.js';

(() => {
  const { READ_ONLY, INITIAL_DATA, API_BASE } = window.__VZ__ || {};
  if (!INITIAL_DATA) { console.error('Hiányzó INITIAL_DATA'); return; }

  // ----- Állapot -----
  const state = {
    counters: INITIAL_DATA.counters || [],
    projects: INITIAL_DATA.projects || [],
    showArchived: false,
    sortMode: 'manual',
    selectedProjects: new Set(), // üres = minden látszik
    calendars: [] // {id,name,events:[]}
  };
  let currentCalendar = null; // épp megnyitott naptár a popupban

  // ----- API -----
  async function apiGet(path) {
    const r = await fetch(`${API_BASE}/${path}`, { credentials: 'same-origin' });
    if (!r.ok) throw new Error(`GET ${path} ${r.status}`);
    return r.json();
  }
  async function apiSend(method, path, body) {
    const r = await fetch(`${API_BASE}/${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'same-origin'
    });
    if (!r.ok) throw new Error(`${method} ${path} ${r.status}`);
    return r.json();
  }
  const api = {
    // Calendars (tartós)
    listCalendars: () => apiGet('calendars'),
    createCalendar: (c) => apiSend('POST', 'calendar', c),
    updateCalendar: (id, patch) => apiSend('PUT', `calendar/${id}`, patch),
    deleteCalendar: (id) => apiSend('DELETE', `calendar/${id}`),
    // Projects
    createProject: (p) => apiSend('POST', 'project', p),
    updateProject: (id, patch) => apiSend('PUT', `project/${id}`, patch),
    deleteProject: (id) => apiSend('DELETE', `project/${id}`),
    // Counters
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

  // Dialog elemek – Counter
  const counterDialog = document.getElementById('counterDialog');
  const counterForm = document.getElementById('counterForm');
  const counterId = document.getElementById('counterId');
  const counterName = document.getElementById('counterName');
  const counterWhen = document.getElementById('counterWhen');
  const counterProject = document.getElementById('counterProject');
  const btnDeleteCounter = document.getElementById('btnDeleteCounter');
  const btnQuickNewProject = document.getElementById('btnQuickNewProject');

  // Dialog elemek – Project
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

  // ICS popup + átnevezés
  const calendarDialog = document.getElementById('calendarDialog');
  const calDlgTitle = document.getElementById('calDlgTitle');
  const calEventsBox = document.getElementById('calEvents');
  const calShowPast = document.getElementById('calShowPast');

  const calendarRenameDialog = document.getElementById('calendarRenameDialog');
  const calendarRenameForm = document.getElementById('calendarRenameForm');
  const calRenameId = document.getElementById('calRenameId');
  const calRenameName = document.getElementById('calRenameName');

  // ----- Init -----
  (async function init() {
    if (READ_ONLY) {
      sidebar.classList.add('hidden');
      modeBadge.textContent = 'Publikus nézet';
      document.getElementById('btnNewCounter').disabled = true;
      document.getElementById('btnNewProject').disabled = true;
      if (icsInput) icsInput.disabled = true;
      if (icsUrlInput) icsUrlInput.disabled = true;
      if (btnIcsFromUrl) btnIcsFromUrl.disabled = true;
      if (emptyHintAdmin) emptyHintAdmin.style.display = 'none';
    } else {
      modeBadge.textContent = 'Admin';
    }

    // Bezár gombok (minden dialogban működik)
    document.querySelectorAll('dialog [data-close]').forEach(b=>{
      b.addEventListener('click', (e)=> e.target.closest('dialog').close());
    });

    // Naptárak betöltése DB-ből (tartós)
    try {
      const rows = await api.listCalendars();
      state.calendars = rows.map(r => {
        const cal = { id: r.id, name: r.name, events: [] };
        try {
          const parsed = parseICS(r.icsText || '');
          cal.events = parsed.events || [];
        } catch (e) {
          console.warn('ICS parse hiba:', r.name, e);
        }
        return cal;
      });
    } catch (e) {
      console.warn('Naptárak betöltése sikertelen:', e);
    }

    // Oldalsáv események
    document.getElementById('btnNewCounter').addEventListener('click', () => {
      if (READ_ONLY) return;
      if (!state.projects.length) state.projects.push({ id: uid('prj'), name: 'Alap', color: '#6ea8fe', font: 'default' });
      openCounterDialog();
    });
    document.getElementById('btnNewProject').addEventListener('click', () => !READ_ONLY && openProjectDialog());

    sortSel.addEventListener('change', () => { state.sortMode = sortSel.value; renderAll(); });
    showArchivedChk.addEventListener('change', () => { state.showArchived = showArchivedChk.checked; renderAll(); });

    // ICS fájl import
    if (icsInput) {
      icsInput.addEventListener('change', async (e) => {
        if (READ_ONLY) return;
        const files = Array.from(e.target.files || []);
        for (const f of files) {
          const text = await f.text();
          const parsed = parseICS(text);
          const calId = uid('cal');
          const name = f.name || 'calendar.ics';
          try {
            await api.createCalendar({ id: calId, name, sourceType: 'inline', url: null, icsText: text });
            state.calendars.push({ id: calId, name, events: parsed.events || [] });
          } catch (err) {
            alert('Naptár mentési hiba: ' + err.message);
          }
        }
        renderCalendars();
        icsInput.value = '';
      });
    }

    // ICS URL import
    if (btnIcsFromUrl) {
      btnIcsFromUrl.addEventListener('click', async () => {
        if (READ_ONLY) return;
        const url = (icsUrlInput?.value || '').trim();
        if (!url) { alert('Adj meg egy .ics URL-t.'); return; }
        try {
          btnIcsFromUrl.disabled = true;
          btnIcsFromUrl.textContent = 'Betöltés...';
          const r = await fetch(`/visszaszamlalo/api/ics_proxy?url=${encodeURIComponent(url)}`, { credentials: 'same-origin' });
          if (!r.ok) throw new Error(await r.text());
          const text = await r.text();
          const parsed = parseICS(text);
          const calId = uid('cal');
          const name = url.split('/').pop() || 'calendar.ics';
          await api.createCalendar({ id: calId, name, sourceType: 'url', url, icsText: text });
          state.calendars.push({ id: calId, name, events: parsed.events || [] });
          renderCalendars();
          icsUrlInput.value = '';
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

    // Naptár átnevezés form
    if (calendarRenameForm) {
      calendarRenameForm.addEventListener('submit', onCalendarRenameSubmit);
    }

    // Múltbéli események mutatása checkbox
    if (calShowPast) {
      calShowPast.addEventListener('change', () => renderCalendarEvents());
    }

    // Kezdeti render + másodperc igazítás
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
    renderCalendars();
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
    emptyEl.style.display = items.length ? 'none' : 'block';

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

  // ----- ICS popup & lista -----
  function openCalendarDialog(cal){
    if (!calendarDialog) return;
    currentCalendar = cal; // eltároljuk melyik naptár van nyitva

    calDlgTitle.textContent = `${cal.name} — ${cal.events.length} esemény`;
    calEventsBox.innerHTML = '';

    // alap: ne mutasson múltbéli eseményeket
    if (calShowPast) calShowPast.checked = false;

    renderCalendarEvents(); // szűr + rendez + kirajzol
    calendarDialog.showModal();
  }

  function renderCalendars(){
    calendarList.innerHTML = '';
    if (!state.calendars.length) {
      const x = document.createElement('div');
      x.className = 'cal-item';
      x.textContent = 'Még nincs elmentett naptár.';
      calendarList.append(x);
      return;
    }

    state.calendars.forEach(cal => {
      const row = document.createElement('div');
      row.className = 'cal-item';

      const top = document.createElement('div');
      top.className = 'row';
      top.style.justifyContent = 'space-between';

      const left = document.createElement('div');
      left.textContent = `${cal.name} — ${cal.events.length} esemény`;

      const right = document.createElement('div');
      right.className = 'row';

      const btnOpen = document.createElement('button');
      btnOpen.className = 'btn secondary';
      btnOpen.type = 'button';
      btnOpen.textContent = 'Megnyitás';
      btnOpen.addEventListener('click', () => openCalendarDialog(cal));
      right.append(btnOpen);

      if (!READ_ONLY) {
        const btnRename = document.createElement('button');
        btnRename.className = 'btn secondary';
        btnRename.type = 'button';
        btnRename.textContent = 'Átnevezés';
        btnRename.addEventListener('click', () => openCalendarRename(cal));
        right.append(btnRename);

        const btnDel = document.createElement('button');
        btnDel.className = 'btn secondary';
        btnDel.type = 'button';
        btnDel.textContent = 'Törlés';
        btnDel.addEventListener('click', async () => {
          if (!confirm('Biztos törlöd a naptárat?')) return;
          try {
            await api.deleteCalendar(cal.id);
            const i = state.calendars.findIndex(x => x.id === cal.id);
            if (i >= 0) state.calendars.splice(i, 1);
            renderCalendars();
          } catch (err) {
            alert('Törlési hiba: ' + err.message);
          }
        });
        right.append(btnDel);
      }

      top.append(left, right);
      row.append(top);

      const hint = document.createElement('small');
      hint.className = 'helper';
      hint.textContent = READ_ONLY
        ? 'Események megtekintése'
        : 'A felugró listában dupla katt egy eseményre → előtöltött számláló létrehozás';
      row.append(hint);

      calendarList.append(row);
    });
  }

  // Események kirajzolása a popupban: szűrés + csökkenő rendezés
  function renderCalendarEvents(){
  if (!currentCalendar) return;
  calEventsBox.innerHTML = '';

  const showPast = !!(calShowPast && calShowPast.checked);

  // Ha NINCS pipa → csak a JÖVŐBELI események (mosttól) látszanak
  const cutoff = showPast ? -Infinity : Date.now();

  // szűrés + csökkenő rendezés (legújabb elöl)
  let items = currentCalendar.events
    .filter(ev => ev.dtstart >= cutoff)
    .sort((a, b) => b.dtstart - a.dtstart);

  // kirajzolás
  items.slice(0, 1000).forEach(ev => {
    const row = document.createElement('div');
    row.className = 'event';
    row.style.cursor = READ_ONLY ? 'default' : 'pointer';

    const left = document.createElement('div');
    left.textContent = ev.summary || '(nincs cím)';

    const right = document.createElement('div');
    right.className = 'when';
    right.textContent = new Date(ev.dtstart).toLocaleString();

    row.append(left, right);

    if (!READ_ONLY) {
      row.title = 'Dupla katt: előtöltött számláló létrehozás';
      row.addEventListener('dblclick', () => {
        if (!state.projects.length) state.projects.push({ id: uid('prj'), name: 'Alap', color: '#6ea8fe', font: 'default' });
        openCounterDialog();
        counterName.value = ev.summary || '';
        counterWhen.value = new Date(ev.dtstart).toISOString().slice(0, 16);
      });
    }

    calEventsBox.append(row);
  });
}

  // ----- Calendar rename -----
  function openCalendarRename(cal) {
    if (!calendarRenameDialog) return;
    calRenameId.value = cal.id;
    calRenameName.value = cal.name || '';
    calendarRenameDialog.showModal();
  }

  async function onCalendarRenameSubmit(e) {
    e.preventDefault();
    if (READ_ONLY) return;
    const id = calRenameId.value;
    const name = calRenameName.value.trim();
    if (!name) { alert('Adj meg nevet.'); return; }
    try {
      await api.updateCalendar(id, { name });
      const cal = state.calendars.find(x => x.id === id);
      if (cal) cal.name = name;
      calendarRenameDialog.close();
      renderCalendars();
      // ha épp nyitva volt, frissítsük a címet is
      if (currentCalendar && currentCalendar.id === id) {
        currentCalendar.name = name;
        calDlgTitle.textContent = `${currentCalendar.name} — ${currentCalendar.events.length} esemény`;
      }
    } catch (err) {
      alert('Mentési hiba: ' + err.message);
    }
  }

})();
