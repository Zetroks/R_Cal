"use strict";
/* Календарь Web: годовая сетка, ховер-плашка, редактор. Vanilla JS. */

const RANK = { none: 0, restricted: 1, viewer: 2, member: 3, editor: 4, owner: 5 };
const GOOGLE_COLORS = [
  ["", "default"], ["1", "Lavender"], ["2", "Sage"], ["3", "Grape"],
  ["4", "Flamingo"], ["5", "Banana"], ["6", "Tangerine"], ["7", "Peacock"],
  ["8", "Graphite"], ["9", "Blueberry"], ["10", "Basil"], ["11", "Tomato"],
];

const S = {
  api: localStorage.getItem("cal_web_api") || "http://127.0.0.1:8011",
  token: null, user: null, pass: null,
  year: new Date().getFullYear(),
  groups: [], groupById: {},
  access: {}, isAdmin: false,
  hidden: new Set(),
  raw: null, byDay: new Map(),
  selected: null, // {y, m, d}
  editing: null,  // {kind, event|null}
  editingGroup: null,
};

const $ = (id) => document.getElementById(id);
const dayKey = (y, m, d) => `${y}-${m}-${d}`;

/* ================= API ================= */

async function loginRequest(user, pass) {
  const r = await fetch(S.api + "/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: user, password: pass }),
  });
  if (!r.ok) throw new Error("Неверный логин или пароль");
  return r.json();
}

async function api(path, opts = {}, retry = true) {
  const headers = Object.assign({}, opts.headers || {});
  if (S.token) headers["Authorization"] = "Bearer " + S.token;
  let r = await fetch(S.api + path, Object.assign({}, opts, { headers }));
  if (r.status === 401 && retry && S.user && S.pass) {
    const data = await loginRequest(S.user, S.pass);
    S.token = data.access_token;
    return api(path, opts, false);
  }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

const apiGet = (path) => api(path);
const apiPost = (path, body) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/* ================= dates ================= */

function parseDT(s) {
  // "2026-07-17 16:00:00.000000" | "2026-10-03 00:00:00"
  const m = /^(\d+)-(\d+)-(\d+)[T ](\d+):(\d+)(?::(\d+))?/.exec(s || "");
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
}

function fmtDate(d) {
  return String(d.getDate()).padStart(2, "0") + "." +
    String(d.getMonth() + 1).padStart(2, "0") + "." + d.getFullYear();
}

function fmtTime(d) {
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

function isAllDay(start, end) {
  return start.getHours() === 0 && start.getMinutes() === 0 &&
    ((end.getHours() === 23 && (end.getMinutes() === 59)) ||
     (end.getHours() === 0 && end.getMinutes() === 0 && end > start));
}

function annualRangeText(e) {
  const s = parseDT(e.start_date), en = parseDT(e.end_date);
  if (!s || !en) return "";
  if (isAllDay(s, en)) {
    return fmtDate(s) === fmtDate(en) || +en - +s <= 24 * 3600 * 1000
      ? fmtDate(s)
      : fmtDate(s) + " – " + fmtDate(en);
  }
  return fmtDate(s) + " " + fmtTime(s) + " – " +
    (fmtDate(s) === fmtDate(en) ? "" : fmtDate(en) + " ") + fmtTime(en);
}

function toInputDT(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* ================= year index ================= */

function buildIndex() {
  S.byDay = new Map();
  const put = (y, m, d, kind, e) => {
    const k = dayKey(y, m, d);
    if (!S.byDay.has(k)) S.byDay.set(k, { annual: [], daily: [] });
    S.byDay.get(k)[kind].push(e);
  };
  for (const e of S.raw.daily || []) put(S.year, e.month, e.day, "daily", e);
  for (const e of S.raw.annual || []) {
    const s = parseDT(e.start_date), en = parseDT(e.end_date);
    if (!s || !en) continue;
    const cur = new Date(s.getFullYear(), s.getMonth(), s.getDate());
    const last = new Date(en.getFullYear(), en.getMonth(), en.getDate());
    let guard = 0;
    while (cur <= last && guard++ < 800) {
      put(cur.getFullYear(), cur.getMonth() + 1, cur.getDate(), "annual", e);
      cur.setDate(cur.getDate() + 1);
    }
  }
}

function dayEvents(y, m, d) {
  return S.byDay.get(dayKey(y, m, d)) || { annual: [], daily: [] };
}

function groupAccess(typeId) {
  if (S.isAdmin) return "owner";
  return S.access[String(typeId)] || S.access[typeId] || "none";
}

function visibleEvents(list) {
  return list.filter((e) => !S.hidden.has(e.type_id));
}

/* ================= render: legend ================= */

function renderLegend() {
  const box = $("legend-list");
  box.innerHTML = "";
  const today = { name: "Сегодня", color: "#FFFF00", id: -1 };
  box.appendChild(legendRow(today, false));
  for (const g of S.groups) box.appendChild(legendRow(g, true));
}

function legendRow(g, real) {
  const row = document.createElement("div");
  row.className = "legend-row" + (real && S.hidden.has(g.id) ? " hidden-group" : "");
  const sw = document.createElement("div");
  sw.className = "swatch";
  sw.style.background = g.color;
  if (real) {
    sw.title = "показать/скрыть";
    sw.onclick = () => {
      if (S.hidden.has(g.id)) S.hidden.delete(g.id); else S.hidden.add(g.id);
      renderLegend(); renderYear();
      if (S.selected) renderEditor();
    };
  }
  const nm = document.createElement("span");
  nm.className = "gname";
  nm.textContent = g.name;
  row.appendChild(sw);
  row.appendChild(nm);
  if (real && (RANK[groupAccess(g.id)] || 0) >= RANK.editor) {
    const eb = document.createElement("button");
    eb.className = "edit-btn";
    eb.textContent = "⚙";
    eb.title = "Редактировать группу";
    eb.onclick = () => openGroupModal(g);
    row.appendChild(eb);
  }
  return row;
}

/* ================= render: year ================= */

const MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function renderYear() {
  $("year-label").textContent = S.year;
  const grid = $("year-grid");
  grid.innerHTML = "";
  const today = new Date();
  for (let m = 1; m <= 12; m++) {
    const box = document.createElement("div");
    box.className = "month";
    const h = document.createElement("h4");
    h.textContent = MONTHS_RU[m - 1];
    box.appendChild(h);
    const mg = document.createElement("div");
    mg.className = "mgrid";
    for (const d of DOW) {
      const c = document.createElement("div");
      c.className = "dow"; c.textContent = d;
      mg.appendChild(c);
    }
    const first = new Date(S.year, m - 1, 1);
    let off = (first.getDay() + 6) % 7; // Monday-first
    const dim = new Date(S.year, m, 0).getDate();
    const prevDim = new Date(S.year, m - 1, 0).getDate();
    for (let i = off - 1; i >= 0; i--) mg.appendChild(dayCell(S.year, m - 1 || 12, prevDim - i, true));
    for (let d = 1; d <= dim; d++) mg.appendChild(dayCell(S.year, m, d, false));
    const tail = (7 - ((off + dim) % 7)) % 7;
    for (let d = 1; d <= tail; d++) mg.appendChild(dayCell(S.year, m + 1 > 12 ? 1 : m + 1, d, true));
    box.appendChild(mg);
    grid.appendChild(box);
  }
  function dayCell(y, m, d, other) {
    const c = document.createElement("div");
    c.className = "day" + (other ? " other" : "");
    if (!other) {
      const ev = dayEvents(y, m, d);
      const vis = visibleEvents(ev.annual).concat(visibleEvents(ev.daily));
      const num = document.createElement("div");
      num.textContent = d;
      c.appendChild(num);
      if (vis.length) {
        const bars = document.createElement("div");
        bars.className = "bars";
        for (const e of vis.slice(0, 3)) {
          const b = document.createElement("div");
          b.className = "bar";
          const g = S.groupById[e.type_id];
          b.style.background = g ? g.color : "#999";
          bars.appendChild(b);
        }
        if (vis.length > 3) {
          const more = document.createElement("div");
          more.className = "more";
          more.textContent = "+" + (vis.length - 3);
          bars.appendChild(more);
        }
        c.appendChild(bars);
      }
      const now = today;
      if (y === now.getFullYear() && m === now.getMonth() + 1 && d === now.getDate()) c.classList.add("today");
      if (S.selected && S.selected.y === y && S.selected.m === m && S.selected.d === d) c.classList.add("selected");
      c.addEventListener("mouseenter", (ev2) => scheduleHint(c, y, m, d, ev2));
      c.addEventListener("mouseleave", hideHint);
      c.onclick = () => {
        S.selected = { y, m, d };
        renderYear(); renderEditor();
      };
    } else {
      c.textContent = d;
    }
    return c;
  }
}

/* ================= tooltip ================= */

let hintTimer = null;
function scheduleHint(cell, y, m, d, ev) {
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => showHint(cell, y, m, d, ev), 400);
}

function showHint(cell, y, m, d, ev) {
  const tip = $("tooltip");
  const evs = dayEvents(y, m, d);
  const visA = visibleEvents(evs.annual), visD = visibleEvents(evs.daily);
  if (!visA.length && !visD.length) { tip.hidden = true; return; }
  let html = `<h4>${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}.${y}</h4>`;
  const item = (e, meta) => {
    const g = S.groupById[e.type_id];
    const col = g ? g.color : "#999";
    const title = String(e.title === "restricted" ? "(занято)" : (e.title || "(без названия)")).replace(/</g, "&lt;");
    return `<div class="t-ev"><span class="dot" style="background:${col}"></span><span>${title}<br><small>${meta}</small></span></div>`;
  };
  for (const e of visA) html += item(e, annualRangeText(e));
  for (const e of visD) html += item(e, "ежегодно");
  tip.innerHTML = html;
  tip.hidden = false;
  const x = Math.min((ev.clientX || 0) + 16, window.innerWidth - 340);
  const y2 = Math.min((ev.clientY || 0) + 16, window.innerHeight - 200);
  tip.style.left = x + "px";
  tip.style.top = y2 + "px";
}

function hideHint() {
  clearTimeout(hintTimer);
  $("tooltip").hidden = true;
}

/* ================= editor panel ================= */

function canEditAny() {
  if (S.isAdmin) return true;
  return S.groups.some((g) => (RANK[groupAccess(g.id)] || 0) >= RANK.editor);
}

function renderEditor() {
  const sel = S.selected;
  const list = $("editor-list");
  list.innerHTML = "";
  if (!sel) { $("editor-title").textContent = "День не выбран"; $("editor-add").hidden = true; return; }
  $("editor-title").textContent = `${String(sel.d).padStart(2, "0")}.${String(sel.m).padStart(2, "0")}.${sel.y}`;
  $("editor-add").hidden = !canEditAny();
  const evs = dayEvents(sel.y, sel.m, sel.d);
  const seen = new Set();
  const card = (kind, e) => {
    const idk = kind + ":" + e.id;
    if (seen.has(idk)) return;
    seen.add(idk);
    const g = S.groupById[e.type_id];
    const div = document.createElement("div");
    div.className = "ev";
    div.style.borderLeft = `4px solid ${g ? g.color : "#999"}`;
    const title = e.title === "restricted" ? "(занято)" : (e.title || "(без названия)");
    const meta = kind === "annual" ? annualRangeText(e) : "ежегодно";
    div.innerHTML = `<div class="ev-title"></div><div class="ev-meta"></div>`;
    div.querySelector(".ev-title").textContent = title;
    div.querySelector(".ev-meta").textContent = meta + (g ? " · " + g.name : "");
    if ((RANK[groupAccess(e.type_id)] || 0) >= RANK.editor || S.isAdmin) {
      const acts = document.createElement("div");
      acts.className = "ev-actions";
      const eb = document.createElement("button");
      eb.textContent = "Изменить";
      eb.onclick = () => openEventModal(kind, e);
      acts.appendChild(eb);
      div.appendChild(acts);
    }
    list.appendChild(div);
  };
  visibleEvents(evs.annual).forEach((e) => card("annual", e));
  visibleEvents(evs.daily).forEach((e) => card("daily", e));
  if (!list.children.length) list.innerHTML = '<div class="muted">Нет событий</div>';
}

/* ================= event modal ================= */

function typeOptions(selectedId) {
  return S.groups
    .filter((g) => S.isAdmin || (RANK[groupAccess(g.id)] || 0) >= RANK.editor)
    .map((g) => `<option value="${g.id}"${g.id === selectedId ? " selected" : ""}>${g.name.replace(/</g, "&lt;")}</option>`)
    .join("");
}

function openEventModal(kind, e) {
  S.editing = { kind, event: e || null };
  const sel = S.selected;
  $("event-modal-title").textContent =
    (e ? "Изменить " : "Новое ") + (kind === "annual" ? "annual" : "daily");
  $("event-error").textContent = "";
  $("event-delete").style.display = e ? "" : "none";
  const f = $("event-form");
  let html = `<label>Название <input id="ef-title" type="text" value="${e ? String(e.title || "").replace(/"/g, "&quot;") : ""}"></label>`;
  html += `<label>Группа <select id="ef-type">${typeOptions(e ? e.type_id : (S.groups[0] && S.groups[0].id))}</select></label>`;
  if (kind === "annual") {
    let sVal = "", eVal = "";
    if (e) {
      const s = parseDT(e.start_date), en = parseDT(e.end_date);
      if (s) sVal = toInputDT(s);
      if (en) eVal = toInputDT(en);
    } else if (sel) {
      const d = `${sel.y}-${String(sel.m).padStart(2, "0")}-${String(sel.d).padStart(2, "0")}`;
      sVal = d + "T12:00"; eVal = d + "T13:00";
    }
    html += `<label>Начало <input id="ef-start" type="datetime-local" value="${sVal}"></label>`;
    html += `<label>Конец <input id="ef-end" type="datetime-local" value="${eVal}"></label>`;
    html += `<label>URL <input id="ef-url" type="text" value="${e && e.url && e.url !== "restricted" ? String(e.url).replace(/"/g, "&quot;") : ""}"></label>`;
  } else {
    const m = e ? e.month : (sel ? sel.m : 1);
    const d = e ? e.day : (sel ? sel.d : 1);
    html += `<label>Месяц <input id="ef-month" type="number" min="1" max="12" value="${m}"></label>`;
    html += `<label>День <input id="ef-day" type="number" min="1" max="31" value="${d}"></label>`;
  }
  f.innerHTML = html;
  $("event-modal").hidden = false;
}

async function saveEventModal() {
  const { kind, event: e } = S.editing;
  const err = $("event-error");
  err.textContent = "";
  try {
    const title = $("ef-title").value.trim();
    const typeId = +$("ef-type").value;
    if (!title) throw new Error("Введите название");
    const payload = {
      action: "upsert",
      kind,
      id: e ? e.id : null,
      title,
      type_id: typeId,
      version: e ? (e.version + 1) : 0,
      is_deleted: false,
      start_date: null, end_date: null, day: null, month: null, url: null,
    };
    if (kind === "annual") {
      const s = $("ef-start").value, en = $("ef-end").value;
      if (!s || !en) throw new Error("Заполните начало и конец");
      payload.start_date = s.length === 16 ? s + ":00" : s;
      payload.end_date = en.length === 16 ? en + ":00" : en;
      payload.url = $("ef-url").value.trim() || null;
    } else {
      payload.month = +$("ef-month").value;
      payload.day = +$("ef-day").value;
      if (!(payload.month >= 1 && payload.month <= 12 && payload.day >= 1 && payload.day <= 31))
        throw new Error("Некорректные день/месяц");
    }
    await apiPost("/event", payload);
    $("event-modal").hidden = true;
    await reloadYear();
  } catch (ex) { err.textContent = ex.message; }
}

async function deleteEventModal() {
  const { kind, event: e } = S.editing;
  if (!e || !confirm("Удалить событие?")) return;
  const err = $("event-error");
  try {
    await apiPost("/event", {
      action: "delete", kind, id: e.id, title: e.title || "x",
      type_id: e.type_id, version: e.version, is_deleted: true,
      start_date: null, end_date: null, day: null, month: null, url: null,
    });
    $("event-modal").hidden = true;
    await reloadYear();
  } catch (ex) { err.textContent = ex.message; }
}

/* ================= group modal ================= */

function openGroupModal(g) {
  S.editingGroup = g;
  $("group-error").textContent = "";
  $("group-sync-status").textContent = "";
  $("group-name").value = g.name || "";
  $("group-color").value = /^#[0-9a-fA-F]{6}$/.test(g.color || "") ? g.color : "#ffffff";
  $("group-sync").checked = !!g.google_sync_enabled;
  $("group-cal").value = (g.google_calendar_id && g.google_calendar_id !== "None") ? g.google_calendar_id : "";
  const gc = $("group-gcolor");
  gc.innerHTML = GOOGLE_COLORS.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  gc.value = g.google_color_id || "";
  $("group-gvis").value = g.google_visibility || "";
  $("group-modal").hidden = false;
}

async function saveGroupModal() {
  const g = S.editingGroup;
  const err = $("group-error");
  err.textContent = "";
  try {
    const resp = await apiPost("/event_type", {
      id: g.id,
      name: $("group-name").value.trim() || g.name,
      color: $("group-color").value,
      google_calendar_id: $("group-cal").value.trim(),
      google_color_id: $("group-gcolor").value,
      google_visibility: $("group-gvis").value,
      google_sync_enabled: $("group-sync").checked,
    });
    const sync = resp.sync;
    if (sync) {
      let msg = `Сохранено. Google sync: вставлено ${sync.inserted || 0}, обновлено ${sync.updated || 0}.`;
      if (sync.errors && sync.errors.length) msg += " Ошибки: " + sync.errors.slice(0, 3).join("; ");
      $("group-sync-status").textContent = msg;
    } else {
      $("group-modal").hidden = true;
    }
    await reloadGroups();
  } catch (ex) { err.textContent = ex.message; }
}

/* ================= load ================= */

async function reloadGroups() {
  const data = await apiGet("/event_types");
  S.groups = data.event_types || [];
  S.groupById = {};
  for (const g of S.groups) S.groupById[g.id] = g;
  renderLegend();
  renderYear();
  if (S.selected) renderEditor();
}

async function reloadYear() {
  $("year-label").textContent = S.year + " …";
  const data = await apiGet(`/year?year=${S.year}`);
  S.raw = data;
  buildIndex();
  renderYear();
  if (S.selected) renderEditor(); else renderEditor();
}

async function enterApp() {
  const [srv, mine] = await Promise.all([
    fetch(S.api + "/version").then((r) => r.json()),
    fetch("app-version").then((r) => r.json()),
  ]);
  if ((mine.protocol || "") < (srv.min_protocol || "")) {
    document.body.innerHTML =
      `<div class="center-wrap"><div class="card"><h2>Нужно обновление</h2>` +
      `<p>Клиент (протокол ${mine.protocol}) несовместим с сервером ` +
      `(требуется >= ${srv.min_protocol}).</p>` +
      `<p><a href="${srv.installer_url}">Скачать новую версию</a></p></div></div>`;
    return;
  }
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("user-label").textContent = S.user + " @ " + S.api;
  const acc = await apiGet("/my_access");
  S.isAdmin = !!acc.IsAdmin;
  S.access = S.isAdmin ? {} : acc;
  await reloadGroups();
  await reloadYear();
}

/* ================= login ================= */

function fillLogin() {
  $("login-server").value = S.api;
  $("login-user").value = localStorage.getItem("cal_web_user") || "";
  const pw = localStorage.getItem("cal_web_pass") || "";
  $("login-pass").value = pw;
  $("login-remember").checked = !!pw || localStorage.getItem("cal_web_remember") === "1";
}

async function doLogin(ev) {
  if (ev) ev.preventDefault();
  const err = $("login-error");
  err.textContent = "";
  const btn = $("login-btn");
  btn.disabled = true;
  try {
    S.api = $("login-server").value.trim().replace(/\/+$/, "") || S.api;
    const user = $("login-user").value.trim();
    const pass = $("login-pass").value;
    if (!user || !pass) throw new Error("Введите пользователя и пароль");
    const data = await loginRequest(user, pass);
    S.token = data.access_token;
    S.user = user; S.pass = pass;
    localStorage.setItem("cal_web_api", S.api);
    localStorage.setItem("cal_web_user", user);
    if ($("login-remember").checked) {
      localStorage.setItem("cal_web_pass", pass);
      localStorage.setItem("cal_web_remember", "1");
    } else {
      localStorage.removeItem("cal_web_pass");
      localStorage.removeItem("cal_web_remember");
    }
    await enterApp();
  } catch (ex) {
    err.textContent = ex.message;
    S.token = null;
  } finally {
    btn.disabled = false;
  }
}

function doLogout() {
  S.token = null; S.user = null; S.pass = null;
  S.groups = []; S.groupById = {}; S.raw = null; S.selected = null;
  S.hidden = new Set();
  $("app-view").hidden = true;
  $("login-view").hidden = false;
  fillLogin();
}

/* ================= wire ================= */

$("login-form").addEventListener("submit", doLogin);
$("logout-btn").onclick = doLogout;
$("year-prev").onclick = () => { S.year--; S.selected = null; reloadYear(); };
$("year-next").onclick = () => { S.year++; S.selected = null; reloadYear(); };
$("add-daily-btn").onclick = () => openEventModal("daily", null);
$("add-annual-btn").onclick = () => openEventModal("annual", null);
$("event-save").onclick = saveEventModal;
$("event-delete").onclick = deleteEventModal;
$("event-cancel").onclick = () => { $("event-modal").hidden = true; };
$("group-save").onclick = saveGroupModal;
$("group-cancel").onclick = () => { $("group-modal").hidden = true; };
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("event-modal").hidden = true;
    $("group-modal").hidden = true;
    hideHint();
  }
});

fillLogin();
