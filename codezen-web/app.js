/* ═══════════════════════════════════════════════════════════
   CodeZen — web client
   Plain HTML/CSS/JS. Talks to the same FastAPI backend as the
   Flutter app. Python step-debugging runs fully client-side via
   Pyodide (real sys.settrace — no LLM, no server round-trip).
   ═══════════════════════════════════════════════════════════ */

const CONFIG = {
  API: localStorage.getItem('cz_api') || 'https://fb9f-2401-4900-8f85-aaa5-c941-2f2d-de26-2d1c.ngrok-free.app/api/v1',
};
const apiRoot = () => CONFIG.API.replace(/\/api\/v1\/?$/, '');

/* ───────────── theme ───────────── */
function applyTheme(t) { document.documentElement.setAttribute('data-theme', t); }
function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  localStorage.setItem('cz_theme', next);
  applyTheme(next);
}
applyTheme(localStorage.getItem('cz_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

/* ───────────── state ───────────── */
const S = {
  token: localStorage.getItem('cz_token') || null,
  user: JSON.parse(localStorage.getItem('cz_user') || 'null'),
  route: '', params: {},
  rooms: [], saved: [],
  editor: { code: '', lang: 'python', roomId: null, trace: null, step: 0, tab: 'output',
            stdout: '', stderr: '', ms: 0, ok: false, review: null, tests: null },
  canvas: { nodes: [], conns: [], sel: null, code: '', badges: [], usedLlm: false, stale: false, drag: null },
  chat: { msgs: [], busy: false, roomId: null },
  iv: { stage: 'pick', topic: null, diff: 'medium', roundType: 'technical_l1', sid: null, msgs: [], fb: null, busy: false, aiSpeaking: false,
    company: null, adaptiveHint: null, _adaptiveFetched: false, _diagnosticFetched: false },
};

/* ───────────── tiny helpers ───────────── */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const initials = n => (n || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
const ago = d => {
  const s = (Date.now() - new Date(d).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
};

const skelRows = (n=3) => `<div class="loading-list">${Array.from({length:n},()=>'<div class="skel skel-row"></div>').join('')}</div>`;
const skelStats = (n=4) => `<div class="grid g4">${Array.from({length:n},()=>'<div class="skel skel-stat"></div>').join('')}</div>`;

function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = '.3s'; setTimeout(() => el.remove(), 300); }, 2600);
}

function modal(html, wide) {
  const bg = document.createElement('div');
  bg.className = 'modal-bg';
  bg.innerHTML = `<div class="modal ${wide ? 'modal-wide' : ''}">${html}</div>`;
  bg.addEventListener('click', e => { if (e.target === bg) bg.remove(); });
  $('#modalRoot').appendChild(bg);
  return bg;
}
const closeModals = () => $$('#modalRoot .modal-bg').forEach(m => m.remove());

/* ───────────── icons ───────────── */
const I = {
  home: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>',
  rooms: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 20V10h6v10"/></svg>',
  code: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="m9 18-6-6 6-6M15 6l6 6-6 6"/></svg>',
  canvas: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="5" rx="1"/><rect x="14" y="16" width="7" height="5" rx="1"/><path d="M6.5 8v4a2 2 0 0 0 2 2h9"/></svg>',
  chat: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-11.7 7.1L4 20l1-4.5A8 8 0 1 1 21 12z"/></svg>',
  mic: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/></svg>',
  chart: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 21h18M7 21V10M12 21V4M17 21v-7"/></svg>',
  book: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22z"/></svg>',
  user: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  play: '<svg fill="currentColor" viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg>',
  bug: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="8" y="6" width="8" height="14" rx="4"/><path d="M3 10h5M16 10h5M3 17h5M16 17h5M9 3l1.5 2M15 3l-1.5 2"/></svg>',
  first: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 5v14M18 6l-8 6 8 6z"/></svg>',
  prev: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6"/></svg>',
  next: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>',
  last: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 5v14M6 6l8 6-8 6z"/></svg>',
  bolt: '<svg fill="currentColor" viewBox="0 0 24 24"><path d="M13 2 3 14h7l-1 8 10-12h-7z"/></svg>',
  spark: '<svg fill="currentColor" viewBox="0 0 24 24"><path d="M12 2l1.8 5.7L19.5 9l-5.7 1.8L12 16.5l-1.8-5.7L4.5 9l5.7-1.3z"/></svg>',
  save: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
  plus: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  send: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  check: '<svg fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M4 12.5 9 17.5 20 6.5"/></svg>',
  trash: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/></svg>',
  logout: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 12H4M8 8l-4 4 4 4M14 4h6v16h-6"/></svg>',
  gauge: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/></svg>',
  fire: '<svg fill="currentColor" viewBox="0 0 24 24"><path d="M12 2s5 5 5 9a5 5 0 0 1-10 0c0-1.5.6-2.8 1.3-3.8C8.7 8.5 12 6 12 2z"/></svg>',
  camera: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  alert: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5v.01"/></svg>',
  eye: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>',
  shield: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2 4 5v6c0 5 3.4 8.4 8 11 4.6-2.6 8-6 8-11V5z"/></svg>',
  micOff: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 3l18 18M9 9v3a3 3 0 0 0 4.6 2.5M15 9V5a3 3 0 0 0-5.9-.8M5 11a7 7 0 0 0 9.6 6.6M19 11a7 7 0 0 1-1 3.6M12 18v4"/></svg>',
  volume: '<svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 8a5 5 0 0 1 0 8M19.5 5.5a9 9 0 0 1 0 13"/></svg>',
  stop: '<svg fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
};

/* ───────────── API ───────────── */
async function api(path, opts = {}) {
  const h = { ...(opts.headers || {}) };
  if (!(opts.body instanceof FormData)) h['Content-Type'] = 'application/json';
  if (S.token) h['Authorization'] = 'Bearer ' + S.token;
  h['ngrok-skip-browser-warning'] = 'true';

  let res;
  try {
    res = await fetch(CONFIG.API + path, { ...opts, headers: h });
  } catch (e) {
    throw new Error('Cannot reach the backend. Is it running at ' + CONFIG.API + ' ?');
  }
  if (res.status === 401) { logout(); throw new Error('Session expired — please sign in again'); }
  if (!res.ok) {
    let d = '';
    try { const j = await res.json(); d = j.detail || JSON.stringify(j); } catch { d = await res.text(); }
    throw new Error(typeof d === 'string' ? d : JSON.stringify(d));
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('json') ? res.json() : res.text();
}
const GET = p => api(p);
const POST = (p, b) => api(p, { method: 'POST', body: JSON.stringify(b) });
const PATCH = (p, b) => api(p, { method: 'PATCH', body: JSON.stringify(b) });
const DEL = p => api(p, { method: 'DELETE' });

function saveAuth(d) {
  S.token = d.access_token; S.user = d.user;
  localStorage.setItem('cz_token', S.token);
  localStorage.setItem('cz_user', JSON.stringify(S.user));
}
function logout() {
  S.token = null; S.user = null;
  localStorage.removeItem('cz_token'); localStorage.removeItem('cz_user');
  location.hash = '#/login';
}
const avatarUrl = u => {
  const a = u?.avatar_url;
  if (!a) return null;
  return a.startsWith('http') ? a : apiRoot() + a;
};

/* ───────────── router ───────────── */
const ROUTES = {
  '/login': viewLogin, '/home': viewHome, '/rooms': viewRooms,
  '/editor': viewEditor, '/canvas': viewCanvas, '/chat': viewChat,
  '/interview': viewInterview, '/progress': viewProgress,
  '/saved': viewSaved, '/profile': viewProfile,
};

function go(h) { location.hash = h; }

function router() {
  const prevRoute = S.route;
  const raw = (location.hash || '#/home').slice(1);
  const [path, ...rest] = raw.split('/').filter(Boolean);
  const route = '/' + (path || 'home');
  S.route = route; S.params = { id: rest[0] || null };

  if (!S.token && route !== '/login') return go('#/login');
  if (S.token && route === '/login') return go('#/home');

  if (prevRoute === '/interview' && route !== '/interview') {
    Proctor.stop(); SpeechOut.stop(); SpeechIn.stop();
    S.iv._precheckStream?.getTracks?.().forEach(t => t.stop());
    S.iv._precheckStream = null; S.iv._precheckMounted = false; S.iv._liveMounted = false;
  }

  const fn = ROUTES[route] || viewHome;
  closeModals();
  fn();
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.r === route));
}
window.addEventListener('hashchange', router);
window.addEventListener('beforeunload', () => { Proctor.stop(); SpeechOut.stop(); });

/* ───────────── shell ───────────── */
function shell(title, sub, body, opts = {}) {
  const av = avatarUrl(S.user);
  const nav = [
    ['/home', 'Home', I.home], ['/rooms', 'Rooms', I.rooms],
    ['/editor', 'Editor', I.code], ['/canvas', 'Algorithm Canvas', I.canvas],
  ];
  const ai = [
    ['/chat', 'AI Tutor', I.chat], ['/interview', 'Mock Interview', I.mic],
    ['/progress', 'Progress', I.chart], ['/saved', 'Saved', I.book],
  ];
  const link = ([r, l, ic]) => `<a class="nav-item" data-r="${r}" href="#${r}">${ic}<span>${l}</span></a>`;

  $('#app').innerHTML = `
    <aside class="sidebar" id="sidebar">
      <div class="brand">
        <div class="brand-mark"><img src="logo.png" alt="CodeZen"></div>
        <div><div class="brand-name">CodeZen</div><div class="brand-sub">learn by drawing</div></div>
      </div>
      <nav class="nav">
        <div class="nav-label">WORKSPACE</div>
        ${nav.map(link).join('')}
        <div class="nav-label">AI TOOLS</div>
        ${ai.map(link).join('')}
      </nav>
      <div class="side-foot">
        <a class="side-user" href="#/profile">
          <div class="avatar">${av ? `<img src="${av}" alt="">` : esc(initials(S.user?.name))}</div>
          <div class="side-user-meta">
            <div class="side-user-name">${esc(S.user?.name || 'You')}</div>
            <div class="side-user-mail">${esc(S.user?.email || '')}</div>
          </div>
        </a>
        <button class="theme-toggle" id="themeToggle" title="Toggle theme" aria-label="Toggle theme">
          <svg class="i-moon" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
          <svg class="i-sun" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
        </button>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        <button class="menu-btn" onclick="document.getElementById('sidebar').classList.toggle('open')">
          <svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
        </button>
        <div style="flex:1;min-width:0">
          <h1>${esc(title)}</h1>
          ${sub ? `<div class="sub">${esc(sub)}</div>` : ''}
        </div>
        ${opts.actions || ''}
      </header>
      ${opts.bare ? body : `<div class="page" id="pageScroll"><div class="page-narrow">${body}</div></div>`}
    </div>`;
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.r === S.route));
  $('#themeToggle')?.addEventListener('click', toggleTheme);
  const ps = $('#pageScroll');
  if (ps) ps.addEventListener('scroll', () => {
    $('.topbar')?.classList.toggle('scrolled', ps.scrollTop > 4);
  });
}

/* ═══════════════ LOGIN ═══════════════ */
function viewLogin() {
  let mode = 'login';
  const render = () => {
    $('#app').innerHTML = `
      <div class="auth-wrap">
        <div class="auth-visual">
          <div class="auth-visual-inner">
            <div class="auth-visual-mark"><img src="logo.png" alt="CodeZen"></div>
            <h2>CodeZen</h2>
            <p>Draw the logic, we compile the code — and you keep the understanding.</p>
            <div class="auth-visual-tags">
              <span>Algorithm Canvas</span><span>AI Tutor that hints, not answers</span>
              <span>Mock Interviews</span><span>Live Rooms</span>
            </div>
          </div>
        </div>
        <div class="auth-panel"><div class="auth-card">
        <div class="auth-brand">
          <div class="brand-mark"><img src="logo.png" alt="CodeZen"></div>
          <div><div class="brand-name" style="font-size:18px">CodeZen</div>
          <div class="brand-sub">learn by drawing, not copying</div></div>
        </div>
        <div class="auth-tabs">
          <button class="auth-tab ${mode === 'login' ? 'active' : ''}" data-m="login">Sign in</button>
          <button class="auth-tab ${mode === 'reg' ? 'active' : ''}" data-m="reg">Create account</button>
        </div>
        <form id="authForm">
          ${mode === 'reg' ? `<div class="field"><label class="label">Name</label>
            <input class="input" name="name" placeholder="Your name" required></div>` : ''}
          <div class="field"><label class="label">Email</label>
            <input class="input" name="email" type="email" placeholder="you@college.edu" required></div>
          <div class="field"><label class="label">Password</label>
            <input class="input" name="password" type="password" placeholder="••••••••" required minlength="8"></div>
          <button class="btn btn-lg" style="width:100%;margin-top:6px" id="authBtn">
            ${mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div></div></div>`;

    $$('.auth-tab').forEach(t => t.onclick = () => { mode = t.dataset.m; render(); });
    $('#authForm').onsubmit = async e => {
      e.preventDefault();
      const btn = $('#authBtn'); btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Please wait';
      const f = Object.fromEntries(new FormData(e.target));
      try {
        const d = await POST(mode === 'login' ? '/auth/login' : '/auth/register', f);
        saveAuth(d); toast('Welcome, ' + (d.user?.name || '') + '!', 'ok'); go('#/home');
      } catch (err) {
        toast(err.message, 'err');
        btn.disabled = false; btn.textContent = mode === 'login' ? 'Sign in' : 'Create account';
      }
    };
  };
  render();
}

/* ═══════════════ HOME ═══════════════ */
async function viewHome() {
  const tools = [
    ['#/canvas', 'Algorithm Canvas', 'Draw logic, get real code', I.canvas, 'var(--cyan)', 'var(--cyan-soft)'],
    ['#/chat', 'AI Tutor', 'Hints, never answers', I.chat, 'var(--purple)', 'var(--purple-soft)'],
    ['#/interview', 'Mock Interview', 'Practice a real round', I.mic, 'var(--amber)', 'var(--amber-soft)'],
    ['#/progress', 'Progress', 'See your weak areas', I.chart, 'var(--green)', 'var(--green-soft)'],
  ];
  shell(`Hi ${(S.user?.name || 'there').split(' ')[0]}`, 'Ready to build something today?', `
    <div class="hero" style="margin-bottom:20px">
      <div class="row between wrap" style="gap:16px">
        <div style="min-width:240px">
          <div style="font-size:20px;font-weight:800;margin-bottom:4px">Draw the logic. We'll write the code.</div>
          <div style="opacity:.92;font-size:13.5px;max-width:460px">
            Sketch your algorithm as a flowchart — a deterministic rule engine turns it into runnable Python. AI only steps in when a label is plain English.
          </div>
        </div>
        <a href="#/canvas" class="btn">${I.bolt} Open Canvas</a>
      </div>
    </div>
    <div id="statRow" style="margin-bottom:22px">${skelStats(4)}</div>
    <div class="section-title">AI Tools</div>
    <div class="tools-grid" style="margin-bottom:24px">
      ${tools.map(([h, t, d, ic, c, bg]) => `<a class="tool" href="${h}">
        <div class="tool-ic" style="background:${bg};color:${c}">${ic}</div>
        <h4>${t}</h4><div class="tiny muted">${d}</div></a>`).join('')}
    </div>
    <div class="row between" style="margin-bottom:12px">
      <div class="section-title" style="margin:0">Your rooms</div>
      <a href="#/rooms" class="btn btn-ghost btn-sm">See all</a>
    </div>
    <div id="roomList">${skelRows(3)}</div>`);

  try {
    const [rooms, prog] = await Promise.all([
      GET('/rooms/').catch(() => []),
      GET('/agent/progress').catch(() => null),
    ]);
    S.rooms = rooms || [];
    const st = (ic, v, l, c, bg) => `<div class="stat">
      <div class="stat-icon" style="background:${bg};color:${c}">${ic}</div>
      <div class="stat-val">${v}</div><div class="stat-lbl">${l}</div></div>`;
    $('#statRow').innerHTML = `<div class="grid g4">` +
      st(I.bolt, S.user?.xp ?? 0, 'XP points', 'var(--cyan)', 'var(--cyan-soft)') +
      st(I.fire, S.user?.streak ?? 0, 'Day streak', 'var(--amber)', 'var(--amber-soft)') +
      st(I.rooms, S.rooms.length, 'Rooms', 'var(--purple)', 'var(--purple-soft)') +
      st(I.check, prog ? (prog.success_rate ?? 0) + '%' : '—', 'Success rate', 'var(--green)', 'var(--green-soft)') +
      `</div>`;

    $('#roomList').innerHTML = S.rooms.length ? S.rooms.slice(0, 4).map(roomRow).join('')
      : `<div class="empty">${I.rooms}<h3>No rooms yet</h3>
         <div class="tiny">Create one to start coding with others</div>
         <a href="#/rooms" class="btn btn-sm" style="margin-top:14px">${I.plus} Create room</a></div>`;
  } catch (e) { toast(e.message, 'err'); }
}

const roomRow = r => `<div class="list-item">
  <div class="item-icon" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.code}</div>
  <div style="flex:1;min-width:0">
    <div style="font-weight:600;font-size:14px">${esc(r.name)}</div>
    <div class="row" style="gap:6px;margin-top:3px">
      <span class="pill pill-cyan">${esc(r.language)}</span>
      ${r.your_role ? `<span class="pill pill-gray">${esc(r.your_role)}</span>` : ''}
    </div>
  </div>
  <a class="btn btn-soft btn-sm" href="#/editor/${r.id}">${I.code} Open</a>
  <a class="btn btn-ghost btn-sm" href="#/chat/${r.id}">${I.chat}</a>
</div>`;

/* ═══════════════ ROOMS ═══════════════ */
async function viewRooms() {
  shell('Rooms', 'Code together in real time', `<div id="rl">${skelRows(4)}</div>`, {
    actions: `<button class="btn btn-ghost btn-sm" id="joinBtn">Join</button>
              <button class="btn btn-sm" id="newBtn">${I.plus} New room</button>`
  });
  $('#newBtn').onclick = newRoomModal;
  $('#joinBtn').onclick = joinRoomModal;
  try {
    S.rooms = await GET('/rooms/');
    $('#rl').innerHTML = S.rooms.length ? S.rooms.map(roomRow).join('')
      : `<div class="empty">${I.rooms}<h3>No rooms yet</h3><div class="tiny">Create your first room</div></div>`;
  } catch (e) { $('#rl').innerHTML = `<div class="empty"><h3>${esc(e.message)}</h3></div>`; }
}

function newRoomModal() {
  const m = modal(`<h3>New room</h3><div class="tiny muted" style="margin-bottom:16px">A shared editor others can join</div>
    <form id="nrf">
      <div class="field"><label class="label">Room name</label>
        <input class="input" name="name" placeholder="DSA practice" required></div>
      <div class="field"><label class="label">Language</label>
        <select class="select" name="language">
          <option value="python">Python</option><option value="java">Java</option>
          <option value="cpp">C++</option><option value="c">C</option></select></div>
      <div class="row" style="gap:8px;margin-top:18px">
        <button type="button" class="btn btn-ghost" style="flex:1" onclick="this.closest('.modal-bg').remove()">Cancel</button>
        <button class="btn" style="flex:1">Create</button></div>
    </form>`);
  $('#nrf', m).onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await POST('/rooms/', Object.fromEntries(new FormData(e.target)));
      m.remove(); toast('Room created', 'ok'); go('#/editor/' + r.id);
    } catch (err) { toast(err.message, 'err'); }
  };
}

function joinRoomModal() {
  const m = modal(`<h3>Join a room</h3><div class="tiny muted" style="margin-bottom:16px">Paste the invite token you were given</div>
    <form id="jrf">
      <div class="field"><input class="input" name="invite_token" placeholder="Invite token" required></div>
      <div class="row" style="gap:8px">
        <button type="button" class="btn btn-ghost" style="flex:1" onclick="this.closest('.modal-bg').remove()">Cancel</button>
        <button class="btn" style="flex:1">Join</button></div>
    </form>`);
  $('#jrf', m).onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await POST('/rooms/join', Object.fromEntries(new FormData(e.target)));
      m.remove(); toast('Joined', 'ok'); go('#/editor/' + r.id);
    } catch (err) { toast(err.message, 'err'); }
  };
}

/* ═══════════════ CLIENT-SIDE PYTHON DEBUGGER (Pyodide) ═══════════════ */
let _pyodide = null, _pyLoading = null;

function loadPyodide_() {
  if (_pyodide) return Promise.resolve(_pyodide);
  if (_pyLoading) return _pyLoading;
  _pyLoading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js';
    s.onload = async () => {
      try { _pyodide = await loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/' }); resolve(_pyodide); }
      catch (e) { reject(e); }
    };
    s.onerror = () => reject(new Error('Could not load the Python engine (needs internet on first use)'));
    document.head.appendChild(s);
  });
  return _pyLoading;
}

const TRACER_PY = `
import sys, json, io, builtins
def _cz_trace(src, limit=400):
    steps, out = [], io.StringIO()
    def safe(v):
        try: r = repr(v)
        except Exception: r = "<unrepr>"
        return r[:160]
    def tracer(frame, event, arg):
        if frame.f_code.co_filename != "<student>":
            return None
        if event == "line" and len(steps) < limit:
            loc = {k: safe(v) for k, v in frame.f_locals.items()
                   if not k.startswith("__") and not callable(v)}
            steps.append({"line": frame.f_lineno, "locals": loc})
        return tracer
    g = {"__name__": "__main__", "__builtins__": builtins}
    err = ""
    old = sys.stdout
    sys.stdout = out
    try:
        code = compile(src, "<student>", "exec")
        sys.settrace(tracer)
        exec(code, g)
    except BaseException as e:
        err = "{}: {}".format(type(e).__name__, e)
    finally:
        sys.settrace(None)
        sys.stdout = old
    return json.dumps({"steps": steps, "stdout": out.getvalue(), "error": err,
                       "truncated": len(steps) >= limit})
`;

async function tracePython(src) {
  const py = await loadPyodide_();
  py.runPython(TRACER_PY);
  const fn = py.globals.get('_cz_trace');
  const raw = fn(src);
  fn.destroy?.();
  return JSON.parse(raw);
}

/* ═══════════════ EDITOR ═══════════════ */
const STARTERS = {
  python: 'def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n\nfor i in range(8):\n    print(i, fib(i))\n',
  java: 'public class Main {\n    public static void main(String[] args) {\n        for (int i = 0; i < 5; i++) {\n            System.out.println("i = " + i);\n        }\n    }\n}\n',
  cpp: '#include <iostream>\nusing namespace std;\n\nint main() {\n    for (int i = 0; i < 5; i++) cout << i << "\\n";\n    return 0;\n}\n',
  c: '#include <stdio.h>\n\nint main() {\n    for (int i = 0; i < 5; i++) printf("%d\\n", i);\n    return 0;\n}\n',
};

async function viewEditor() {
  const E = S.editor;
  E.roomId = S.params.id || null;
  if (!E.code) E.code = STARTERS[E.lang];

  shell('Code Editor', E.roomId ? 'Room session' : 'Scratch pad', `
    <div class="editor-shell">
      <div class="editor-bar">
        <select class="select" id="langSel" style="width:auto;padding:7px 10px;font-size:13px">
          ${['python', 'java', 'cpp', 'c'].map(l => `<option value="${l}" ${E.lang === l ? 'selected' : ''}>${l === 'cpp' ? 'C++' : l[0].toUpperCase() + l.slice(1)}</option>`).join('')}
        </select>
        <button class="btn btn-green btn-sm" id="runBtn">${I.play} Run</button>
        <button class="btn btn-amber btn-sm" id="dbgBtn">${I.bug} Debug</button>
        <div style="flex:1"></div>
        <button class="btn btn-ghost btn-sm" id="cxBtn">${I.gauge} Complexity</button>
        <button class="btn btn-ghost btn-sm" id="saveCodeBtn">${I.book} Save</button>
        <button class="btn btn-soft btn-sm" id="revBtn">${I.spark} AI Review</button>
      </div>
      <div class="editor-split">
        <div class="editor-pane">
          <div class="editor-head"><span id="fileName">main.py</span>
            <span style="flex:1"></span><span id="lineInfo"></span></div>
          <div class="code-area">
            <div class="gutter" id="gutter"></div>
            <textarea id="codeInput" spellcheck="false" wrap="off"></textarea>
          </div>
        </div>
        <div class="side-panel" id="sidePanel">
          <div class="sp-tabs">
            <button class="sp-tab active" data-t="output">Output</button>
            <button class="sp-tab" data-t="debug">Debugger</button>
            <button class="sp-tab" data-t="ai">AI</button>
          </div>
          <div class="sp-body" id="spBody"></div>
        </div>
      </div>
    </div>`, { bare: true });

  const ta = $('#codeInput');
  ta.value = E.code;
  const sync = () => {
    E.code = ta.value;
    const n = ta.value.split('\n').length;
    const hit = E.trace?.steps?.[E.step]?.line;
    $('#gutter').innerHTML = Array.from({ length: Math.max(n, 1) },
      (_, i) => `<div class="${hit === i + 1 ? 'hit' : ''}">${i + 1}</div>`).join('');
    $('#fileName').textContent = 'main' + ({ python: '.py', java: '.java', cpp: '.cpp', c: '.c' }[E.lang]);
  };
  ta.addEventListener('input', sync);
  ta.addEventListener('scroll', () => { $('#gutter').scrollTop = ta.scrollTop; });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const s = ta.selectionStart;
      ta.value = ta.value.slice(0, s) + '    ' + ta.value.slice(ta.selectionEnd);
      ta.selectionStart = ta.selectionEnd = s + 4; sync();
    }
  });
  sync();

  if (E.roomId) {
    try { const r = await GET('/rooms/' + E.roomId); if (r.code) { ta.value = r.code; E.lang = r.language || E.lang; $('#langSel').value = E.lang; sync(); } } catch { }
  }

  $('#langSel').onchange = e => {
    E.lang = e.target.value;
    if (!ta.value.trim() || Object.values(STARTERS).includes(ta.value)) { ta.value = STARTERS[E.lang]; }
    E.trace = null; sync(); paintPanel();
  };
  $$('.sp-tab').forEach(t => t.onclick = () => {
    $$('.sp-tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active'); E.tab = t.dataset.t; paintPanel();
  });
  $('#runBtn').onclick = runCode;
  $('#dbgBtn').onclick = debugCode;
  $('#cxBtn').onclick = analyzeComplexity;
  $('#revBtn').onclick = aiReview;
  $('#saveCodeBtn').onclick = async () => {
    const btn = $('#saveCodeBtn'); btn.disabled = true;
    try {
      const firstLine = (ta.value.split('\n').find(l => l.trim()) || 'Untitled').trim().slice(0, 40);
      await POST('/saved', {
        item_type: 'editor_code',
        title: `${firstLine}${firstLine.length >= 40 ? '…' : ''} · ${E.lang}`,
        payload: { code: ta.value, language: E.lang },
      });
      toast('Code saved', 'ok');
    } catch (e) { toast(e.message, 'err'); }
    btn.disabled = false;
  };
  paintPanel();

  function setTab(t) {
    E.tab = t;
    $$('.sp-tab').forEach(x => x.classList.toggle('active', x.dataset.t === t));
    paintPanel();
  }

  function paintPanel() {
    const b = $('#spBody');
    if (!b) return;
    if (E.tab === 'output') {
      b.innerHTML = (!E.stdout && !E.stderr)
        ? `<div class="empty" style="color:#5A7E8C">${I.play}<h3 style="color:#8FB3C0">Nothing run yet</h3>
           <div class="tiny">Hit Run to execute your code</div></div>`
        : `<div class="row" style="gap:8px;margin-bottom:12px">
             <span class="pill ${E.ok ? 'pill-green' : 'pill-red'}">${E.ok ? '✓ Success' : '✗ Error'}</span>
             <span class="tiny" style="color:#6E93A1">${E.ms}ms</span></div>
           ${E.stdout ? `<div class="sp-label">STDOUT</div><div class="out-block">${esc(E.stdout)}</div>` : ''}
           ${E.stderr ? `<div class="sp-label">STDERR</div><div class="out-block out-err">${esc(E.stderr)}</div>` : ''}`;
    }
    else if (E.tab === 'debug') {
      if (E.lang !== 'python') {
        b.innerHTML = `<div class="empty" style="color:#5A7E8C">${I.bug}
          <h3 style="color:#8FB3C0">Step-through is Python-only</h3>
          <div class="tiny" style="max-width:280px;margin:0 auto">
          The debugger runs a real CPython tracer inside your browser. ${E.lang === 'cpp' ? 'C++' : E.lang.toUpperCase()} has no
          browser runtime, so it can still <b>Run</b> on the sandbox but cannot be stepped line by line.</div></div>`;
        return;
      }
      if (!E.trace) {
        b.innerHTML = `<div class="empty" style="color:#5A7E8C">${I.bug}<h3 style="color:#8FB3C0">No trace yet</h3>
          <div class="tiny">Hit Debug to step through your code</div></div>`;
        return;
      }
      const st = E.trace.steps[E.step] || {};
      const vars = Object.entries(st.locals || {});
      const totalSteps = E.trace.steps.length || 0;
      const curStep = Number.isInteger(E.step) ? E.step : 0;
      b.innerHTML = `
        <div class="dbg-ctrl" style="margin:-14px -14px 14px">
          <button class="dbg-btn" id="dFirst" ${curStep === 0 ? 'disabled' : ''}>${I.first}</button>
          <button class="dbg-btn" id="dPrev" ${curStep === 0 ? 'disabled' : ''}>${I.prev}</button>
          <span class="dbg-step">${curStep + 1} / ${totalSteps}</span>
          <button class="dbg-btn" id="dNext" ${curStep >= totalSteps - 1 ? 'disabled' : ''}>${I.next}</button>
          <button class="dbg-btn" id="dLast" ${curStep >= totalSteps - 1 ? 'disabled' : ''}>${I.last}</button>
          <span style="flex:1"></span>
          <span class="tiny" style="color:#6E93A1">line ${st.line ?? '—'}</span>
        </div>
        <div class="sp-label">VARIABLES AT THIS LINE</div>
        ${vars.length ? vars.map(([k, v]) => `<div class="var-row"><span class="var-k">${esc(k)}</span>
            <span style="color:#4A6B78">=</span><span class="var-v">${esc(v)}</span></div>`).join('')
          : '<div class="tiny" style="color:#6E93A1">No local variables yet</div>'}
        ${E.trace.stdout ? `<div class="sp-label">OUTPUT SO FAR</div><div class="out-block">${esc(E.trace.stdout)}</div>` : ''}
        ${E.trace.error ? `<div class="sp-label">ERROR</div><div class="out-block out-err">${esc(E.trace.error)}</div>` : ''}
        ${E.trace.truncated ? `<div class="tiny" style="color:var(--amber);margin-top:10px">Trace capped at 400 steps</div>` : ''}`;
      const step = d => { E.step = Math.max(0, Math.min(E.trace.steps.length - 1, (E.step || 0) + d)); paintPanel(); sync(); };
      $('#dFirst').onclick = () => { E.step = 0; paintPanel(); sync(); };
      $('#dPrev').onclick = () => step(-1);
      $('#dNext').onclick = () => step(1);
      $('#dLast').onclick = () => { E.step = E.trace.steps.length - 1; paintPanel(); sync(); };
    }
    else {
      b.innerHTML = `${E.review ? renderReview(E.review) : ''}${E.tests ? renderTests(E.tests) : ''}
        ${!E.review && !E.tests ? `<div class="empty" style="color:#5A7E8C">${I.spark}
          <h3 style="color:#8FB3C0">No AI output yet</h3>
          <div class="tiny">Run <b>AI Review</b> to get bugs, style and complexity feedback</div>
          <button class="btn btn-sm" style="margin-top:14px" onclick="czTests()">Generate test cases</button></div>` : ''}`;
    }
  }

  async function runCode() {
    const btn = $('#runBtn'); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Running';
    setTab('output');
    try {
      const r = await POST('/canvas/run', { code: ta.value, language: E.lang });
      E.stdout = r.stdout || ''; E.stderr = r.stderr || '';
      E.ms = r.runtime_ms || 0; E.ok = !!r.is_success;
    } catch (e) { E.stdout = ''; E.stderr = e.message; E.ok = false; }
    btn.disabled = false; btn.innerHTML = I.play + ' Run';
    paintPanel();
  }

  async function debugCode() {
    setTab('debug');
    if (E.lang !== 'python') { paintPanel(); return; }
    const btn = $('#dbgBtn'); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Tracing';
    $('#spBody').innerHTML = `<div class="empty" style="color:#5A7E8C"><span class="spinner"></span>
      <h3 style="color:#8FB3C0;margin-top:12px">Starting Python engine…</h3>
      <div class="tiny">First run downloads it once, then it is instant</div></div>`;
    try {
      E.trace = await tracePython(ta.value);
      E.step = 0;
      if (!E.trace.steps.length) toast('Nothing to step through', 'err');
    } catch (e) { toast(e.message, 'err'); E.trace = null; }
    btn.disabled = false; btn.innerHTML = I.bug + ' Debug';
    paintPanel(); sync();
  }

  async function analyzeComplexity() {
    const btn = $('#cxBtn'); btn.disabled = true;
    try {
      const c = await POST('/canvas/analyze', { code: ta.value, language: E.lang });
      const confNum = Number(c.confidence);
      const confPct = Number.isFinite(confNum) ? Math.round(confNum * 100) : null;
      modal(`<h3>Complexity analysis</h3>
        <div class="row" style="gap:8px;margin:14px 0">
          <span class="pill pill-cyan">Time ${esc(c.time_complexity || 'unknown')}</span>
          <span class="pill pill-purple">Space ${esc(c.space_complexity || 'unknown')}</span>
          ${confPct !== null ? `<span class="pill pill-gray">${confPct}% confident</span>` : ''}</div>
        <p style="font-size:13.5px;color:var(--ink-2);line-height:1.6">${esc(c.explanation || '')}</p>
        ${(c.suggestions || []).length ? `<div class="sp-label" style="color:var(--muted)">SUGGESTIONS</div>
          <ul style="padding-left:18px;font-size:13px;color:var(--ink-2);line-height:1.7">
          ${c.suggestions.map(s => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}
        <button class="btn btn-ghost" style="width:100%;margin-top:18px"
          onclick="this.closest('.modal-bg').remove()">Close</button>`);
    } catch (e) { toast(e.message, 'err'); }
    btn.disabled = false;
  }

  async function aiReview() {
    const btn = $('#revBtn'); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Reviewing';
    setTab('ai');
    $('#spBody').innerHTML = `<div class="empty" style="color:#5A7E8C"><span class="spinner"></span>
      <h3 style="color:#8FB3C0;margin-top:12px">Reviewing your code…</h3></div>`;
    try {
      const r = await POST('/agent/message', { message: 'review my code', code: ta.value, language: E.lang, intent: 'code_review' });
      E.review = r.data || r;
    } catch (e) { toast(e.message, 'err'); }
    btn.disabled = false; btn.innerHTML = I.spark + ' AI Review';
    paintPanel();
  }

  window.czTests = async () => {
    $('#spBody').innerHTML = `<div class="empty" style="color:#5A7E8C"><span class="spinner"></span>
      <h3 style="color:#8FB3C0;margin-top:12px">Generating and running test cases…</h3></div>`;
    try {
      const r = await POST('/agent/message', { message: 'give me test cases', code: ta.value, language: E.lang, intent: 'test_cases' });
      E.tests = r.data || r;
    } catch (e) { toast(e.message, 'err'); }
    paintPanel();
  };
}

const renderReview = r => `
  <div class="row" style="gap:10px;margin-bottom:12px">
    <div style="width:46px;height:46px;border-radius:50%;display:grid;place-items:center;
      background:${(r.overall_score ?? 0) >= 7 ? 'rgba(18,161,95,.18)' : 'rgba(217,139,11,.18)'};
      color:${(r.overall_score ?? 0) >= 7 ? '#3ED18F' : '#F0B95B'};font-weight:800;font-size:13px">
      ${r.overall_score ?? '?'}/10</div>
    <div style="flex:1;font-size:13px;line-height:1.5">${esc(r.summary || '')}</div></div>
  ${sec('WHAT YOU DID WELL', r.good, '#3ED18F')}
  ${sec('POTENTIAL BUGS', r.bugs, '#FF9BA4')}
  ${sec('STYLE', r.style, '#F0B95B')}
  ${r.complexity ? `<div class="sp-label">COMPLEXITY</div>
    <div class="out-block">${esc(r.complexity.current || '')}${r.complexity.note ? '\n\n' + esc(r.complexity.note) : ''}</div>` : ''}
  <button class="btn btn-sm" style="width:100%;margin-top:14px" onclick="czTests()">Generate test cases</button>`;

const sec = (t, arr, c) => (arr && arr.length) ? `<div class="sp-label">${t}</div>` +
  arr.map(x => `<div style="display:flex;gap:8px;margin-bottom:7px;font-size:12.5px;line-height:1.55">
    <span style="color:${c};flex-shrink:0">▸</span><span>${esc(x)}</span></div>`).join('') : '';

const renderTests = t => {
  const res = t.results || t.test_results || [];
  if (!res.length) {
    const generated = t.test_cases || t.tests || [];
    return `<div class="sp-label">TEST CASES</div>
      <div class="tiny" style="color:${t.error ? '#FF9BA4' : '#8FB3C0'};margin-bottom:10px">
        ${t.error ? esc(t.error) : (generated.length ? `${generated.length} test case(s) generated but not executed yet.` : 'No test cases available.')}
      </div>
      ${generated.map(g => `<div class="out-block" style="margin-bottom:8px">
        <div style="color:#818CF8;font-weight:600;margin-bottom:4px">${esc(g.name || g.description || 'Case')}</div>
        ${g.input !== undefined ? `<div style="color:#8FB3C0;font-size:11.5px">Input: ${esc(String(g.input))}</div>` : ''}
        ${g.expected_output !== undefined ? `<div style="color:#8FB3C0;font-size:11.5px">Expected: ${esc(String(g.expected_output))}</div>` : ''}
      </div>`).join('')}
      ${t.error ? `<button class="btn btn-sm" style="margin-top:6px" onclick="czTests()">Try again</button>` : ''}`;
  }
  const pass = res.filter(r => r.passed).length;
  return `<div class="sp-label">TEST CASES (${pass}/${res.length} ran clean)</div>
    ${res.map(r => `<div class="out-block" style="margin-bottom:8px;border-color:${r.passed ? 'rgba(18,161,95,.35)' : 'rgba(214,69,80,.35)'}">
      <div style="color:${r.passed ? '#3ED18F' : '#FF9BA4'};font-weight:700;margin-bottom:4px">
        ${r.passed ? '✓' : '✗'} ${esc(r.name || 'Test')}</div>
      <div style="color:#8FB3C0;font-size:11.5px;margin-bottom:6px">${esc(r.description || '')}</div>
      ${r.stdout ? esc(r.stdout.trim()) : ''}${r.stderr ? `<div style="color:#FF9BA4">${esc(r.stderr.trim())}</div>` : ''}
    </div>`).join('')}`;
};

/* ═══════════════ ALGORITHM CANVAS ═══════════════ */
const SHAPES = {
  start:    { w: 130, h: 50, fill: '#DFF7EC', stroke: '#12A15F', text: '#0A6B3F', label: 'Start' },
  process:  { w: 170, h: 58, fill: '#E2F7FA', stroke: '#0E9AA7', text: '#0A5B63', label: 'Process' },
  decision: { w: 172, h: 84, fill: '#FDF3E0', stroke: '#D98B0B', text: '#8A5A06', label: 'Decision' },
  input:    { w: 170, h: 58, fill: '#EFEAFC', stroke: '#7A5CD6', text: '#4A3690', label: 'Input' },
  end:      { w: 130, h: 50, fill: '#F1F5F7', stroke: '#5B7683', text: '#33505C', label: 'End' },
};
const DEFAULT_LABEL = { start: 'START', end: 'END', process: 'print("Hello")', decision: 'x > 0', input: 'x' };
const PORTS = ['top', 'right', 'bottom', 'left'];
const portPos = (n, side) => {
  const s = SHAPES[n.type];
  if (side === 'top') return { x: n.x, y: n.y - s.h / 2 };
  if (side === 'bottom') return { x: n.x, y: n.y + s.h / 2 };
  if (side === 'left') return { x: n.x - s.w / 2, y: n.y };
  return { x: n.x + s.w / 2, y: n.y };
};
const portLabel = (n, side) => n.type === 'decision' ? (side === 'bottom' ? 'YES' : side === 'right' ? 'NO' : '') : '';

function viewCanvas() {
  const C = S.canvas;
  shell('Algorithm Canvas', 'Draw the logic — we compile it to real Python', `
    <div class="canvas-shell">
      <div class="canvas-tools">
        <span class="tiny muted" style="font-weight:600">Add:</span>
        ${Object.entries(SHAPES).map(([k, s]) => `<button class="shape-btn" data-add="${k}"
          style="border-color:${s.stroke};color:${s.stroke}">${s.label}</button>`).join('')}
        <div style="flex:1"></div>
        <button class="btn btn-ghost btn-sm" id="tplBtn">Templates</button>
        <button class="btn btn-ghost btn-sm" id="clrBtn">Clear</button>
        <button class="btn btn-sm" id="genBtn">${I.bolt} Generate Code</button>
      </div>
      <div class="canvas-body">
        <div class="canvas-stage" id="stage">
          <div class="canvas-inner" id="cvInner">
            <svg class="canvas-svg" id="cvSvg"></svg>
          </div>
        </div>
        <div class="canvas-side">
          <div class="sp-tabs" style="background:var(--surface-2);border-bottom:1px solid var(--line)">
            <button class="sp-tab active" style="color:var(--cyan-dark)">Generated code</button>
          </div>
          <div style="padding:12px;border-bottom:1px solid var(--line)" id="cvMeta"></div>
          <textarea id="cvCode" class="mono" spellcheck="false"
            style="flex:1;border:none;outline:none;resize:none;padding:14px;font-size:12.5px;
            line-height:1.65;background:var(--editor-bg);color:#DDEEF3"></textarea>
          <div style="padding:12px;border-top:1px solid var(--line);display:flex;gap:8px">
            <button class="btn btn-green btn-sm" style="flex:1" id="cvRun">${I.play} Run</button>
            <button class="btn btn-ghost btn-sm" id="cvSave">${I.save} Save</button>
          </div>
          <div id="cvOut"></div>
        </div>
      </div>
    </div>`, { bare: true });

  const inner = $('#cvInner'), svg = $('#cvSvg');

  $$('[data-add]').forEach(b => b.onclick = () => {
    const t = b.dataset.add;
    const st = $('#stage');
    C.nodes.push({
      id: 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
      type: t, label: DEFAULT_LABEL[t],
      x: st.scrollLeft + st.clientWidth / 2 + (Math.random() * 60 - 30),
      y: st.scrollTop + 140 + C.nodes.length % 6 * 92,
    });
    C.stale = true; draw();
  });
  $('#clrBtn').onclick = () => {
    if (!C.nodes.length || confirm('Clear the whole canvas?')) {
      C.nodes = []; C.conns = []; C.code = ''; C.badges = []; C.usedLlm = false;
      $('#cvCode').value = ''; draw();
    }
  };
  $('#tplBtn').onclick = templateModal;
  $('#genBtn').onclick = generate;
  $('#cvRun').onclick = runCanvas;
  $('#cvSave').onclick = saveCanvas;
  $('#cvCode').oninput = e => { C.code = e.target.value; };
  $('#cvCode').value = C.code;
  draw();

  function draw() {
    $$('.node', inner).forEach(n => n.remove());
    let paths = '';
    for (const c of C.conns) {
      const a = C.nodes.find(n => n.id === c.from), b = C.nodes.find(n => n.id === c.to);
      if (!a || !b) continue;
      const p1 = portPos(a, c.fromPort), p2 = portPos(b, c.toPort);
      const dy = (p2.y - p1.y) * .5;
      paths += `<path d="M${p1.x} ${p1.y} C${p1.x} ${p1.y + dy},${p2.x} ${p2.y - dy},${p2.x} ${p2.y}"
        fill="none" stroke="#8FB3C0" stroke-width="2" marker-end="url(#ah)"/>`;
      const lb = portLabel(a, c.fromPort);
      if (lb) paths += `<rect x="${(p1.x + p2.x) / 2 - 16}" y="${(p1.y + p2.y) / 2 - 19}" width="32" height="16"
          rx="8" fill="#FDF3E0" stroke="#D98B0B"/><text x="${(p1.x + p2.x) / 2}" y="${(p1.y + p2.y) / 2 - 7}"
          text-anchor="middle" font-size="9" font-weight="700" fill="#8A5A06">${lb}</text>`;
    }
    if (C.drag) {
      const p = portPos(C.drag.node, C.drag.side);
      paths += `<path d="M${p.x} ${p.y} L${C.drag.x} ${C.drag.y}" stroke="#0E9AA7"
        stroke-width="2.5" stroke-dasharray="5 4" fill="none"/>
        <circle cx="${C.drag.x}" cy="${C.drag.y}" r="5" fill="#0E9AA7"/>`;
    }
    svg.innerHTML = `<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="8" refY="4.5"
      orient="auto"><path d="M0,1 L8,4.5 L0,8 z" fill="#8FB3C0"/></marker></defs>${paths}`;

    for (const n of C.nodes) {
      const s = SHAPES[n.type];
      const el = document.createElement('div');
      el.className = 'node' + (C.sel === n.id ? ' sel' : '');
      el.style.cssText = `left:${n.x - s.w / 2}px;top:${n.y - s.h / 2}px;width:${s.w}px;height:${s.h}px;color:${s.text}`;
      const shape = n.type === 'decision'
        ? `<polygon points="${s.w / 2},2 ${s.w - 2},${s.h / 2} ${s.w / 2},${s.h - 2} 2,${s.h / 2}" fill="${s.fill}" stroke="${s.stroke}" stroke-width="2"/>`
        : n.type === 'input'
          ? `<polygon points="${s.w * .13},2 ${s.w - 2},2 ${s.w * .87},${s.h - 2} 2,${s.h - 2}" fill="${s.fill}" stroke="${s.stroke}" stroke-width="2"/>`
          : `<rect x="2" y="2" width="${s.w - 4}" height="${s.h - 4}" rx="${n.type === 'start' || n.type === 'end' ? s.h / 2 : 9}" fill="${s.fill}" stroke="${s.stroke}" stroke-width="2"/>`;
      el.innerHTML = `<svg class="node-shape" width="${s.w}" height="${s.h}">${shape}</svg>
        <span style="padding:0 ${n.type === 'decision' ? 20 : 8}px;pointer-events:none;
          max-height:100%;overflow:hidden">${esc(n.label)}</span>
        ${C.badges.includes(n.id) ? '<span class="ai-badge">AI</span>' : ''}
        ${PORTS.map(p => { const q = portPos(n, p); return `<div class="port" data-node="${n.id}" data-side="${p}"
          style="left:${q.x - n.x + s.w / 2 - 7.5}px;top:${q.y - n.y + s.h / 2 - 7.5}px"></div>`; }).join('')}`;
      inner.appendChild(el);
      wireNode(el, n);
    }
  }

  function wireNode(el, n) {
    let moved = false;
    el.addEventListener('pointerdown', e => {
      if (e.target.classList.contains('port')) return;
      e.preventDefault();
      moved = false;
      const sx = e.clientX, sy = e.clientY, ox = n.x, oy = n.y;
      C.sel = n.id;
      const mv = ev => {
        if (Math.abs(ev.clientX - sx) > 3 || Math.abs(ev.clientY - sy) > 3) moved = true;
        n.x = ox + (ev.clientX - sx); n.y = oy + (ev.clientY - sy);
        C.stale = true; draw();
      };
      const up = () => {
        document.removeEventListener('pointermove', mv);
        document.removeEventListener('pointerup', up);
        if (!moved) editNode(n);
      };
      document.addEventListener('pointermove', mv);
      document.addEventListener('pointerup', up);
    });
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      if (confirm('Delete this shape?')) {
        C.nodes = C.nodes.filter(x => x.id !== n.id);
        C.conns = C.conns.filter(c => c.from !== n.id && c.to !== n.id);
        C.stale = true; draw();
      }
    });
    $$('.port', el).forEach(p => p.addEventListener('pointerdown', e => {
      e.stopPropagation(); e.preventDefault();
      const st = $('#stage'), r = st.getBoundingClientRect();
      C.drag = { node: n, side: p.dataset.side, x: n.x, y: n.y };
      const mv = ev => {
        C.drag.x = ev.clientX - r.left + st.scrollLeft;
        C.drag.y = ev.clientY - r.top + st.scrollTop;
        let hot = null;
        for (const m of C.nodes) {
          if (m.id === n.id) continue;
          for (const side of PORTS) {
            const q = portPos(m, side);
            if (Math.hypot(q.x - C.drag.x, q.y - C.drag.y) < 34) hot = { m, side };
          }
        }
        C.drag.hot = hot; draw();
      };
      const up = () => {
        document.removeEventListener('pointermove', mv);
        document.removeEventListener('pointerup', up);
        if (C.drag?.hot) {
          const { m, side } = C.drag.hot;
          if (!C.conns.some(c => c.from === n.id && c.to === m.id)) {
            C.conns.push({ from: n.id, fromPort: C.drag.side, to: m.id, toPort: side });
            C.stale = true; toast('Connected', 'ok');
          }
        }
        C.drag = null; draw();
      };
      document.addEventListener('pointermove', mv);
      document.addEventListener('pointerup', up);
    }));
  }

  function editNode(n) {
    const hint = { start: 'START, or a function name + params', end: 'END, or a value to return',
      decision: 'A condition (x > 0) or a loop header (for i = 1 to n)',
      process: 'One or more statements — plain English is fine',
      input: 'A variable name' }[n.type];
    const m = modal(`<h3>Edit ${SHAPES[n.type].label.toLowerCase()}</h3>
      <div class="tiny muted" style="margin-bottom:14px">${esc(hint)}</div>
      <textarea class="textarea mono" id="lblIn" rows="4" style="font-size:13px">${esc(n.label)}</textarea>
      <div class="row" style="gap:8px;margin-top:16px">
        <button class="btn btn-danger btn-sm" id="delN">${I.trash}</button>
        <div style="flex:1"></div>
        <button class="btn btn-ghost" onclick="this.closest('.modal-bg').remove()">Cancel</button>
        <button class="btn" id="okN">Apply</button></div>`);
    const ta = $('#lblIn', m); ta.focus(); ta.select();
    $('#okN', m).onclick = () => { n.label = ta.value.trim(); C.stale = true; m.remove(); draw(); };
    $('#delN', m).onclick = () => {
      C.nodes = C.nodes.filter(x => x.id !== n.id);
      C.conns = C.conns.filter(c => c.from !== n.id && c.to !== n.id);
      C.stale = true; m.remove(); draw();
    };
    ta.onkeydown = e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#okN', m).click(); };
  }

  async function generate() {
    if (!C.nodes.length) return toast('Draw a flowchart first', 'err');
    const b = $('#genBtn'); b.disabled = true; b.innerHTML = '<span class="spinner"></span> Generating';
    try {
      const r = await POST('/canvas/generate', {
        nodes: C.nodes.map(n => ({ id: n.id, type: n.type, label: n.label, x: n.x, y: n.y })),
        connections: C.conns.map(c => ({ fromNodeId: c.from, toNodeId: c.to, label: portLabel(C.nodes.find(n => n.id === c.from) || {}, c.fromPort) })),
        language: 'python',
      });
      C.code = r.code || ''; C.badges = r.llm_badge_nodes || [];
      C.usedLlm = !!r.used_llm; C.stale = false;
      $('#cvCode').value = C.code;
      $('#cvMeta').innerHTML = `<div class="row wrap" style="gap:6px">
        ${C.usedLlm ? `<span class="pill pill-purple">${I.spark} AI decoded ${r.dirty_count} node${r.dirty_count === 1 ? '' : 's'}</span>` : '<span class="pill pill-green">Rule engine only — no AI needed</span>'}
        <span class="pill pill-gray">${C.nodes.length} shapes</span></div>`;
      toast(C.usedLlm ? `AI decoded ${r.dirty_count} pseudocode node(s)` : 'Code generated', 'ok');
      draw();
    } catch (e) { toast(e.message, 'err'); }
    b.disabled = false; b.innerHTML = I.bolt + ' Generate Code';
  }

  async function runCanvas() {
    const code = $('#cvCode').value.trim();
    if (!code) return toast('Generate code first', 'err');
    const b = $('#cvRun'); b.disabled = true; b.innerHTML = '<span class="spinner"></span>';
    try {
      const r = await POST('/canvas/run', { code, language: 'python' });
      $('#cvOut').innerHTML = `<div style="padding:12px;border-top:1px solid var(--line);max-height:200px;overflow:auto">
        <div class="row" style="gap:8px;margin-bottom:8px">
          <span class="pill ${r.is_success ? 'pill-green' : 'pill-red'}">${r.is_success ? '✓ Success' : '✗ Error'}</span>
          <span class="tiny muted">${r.runtime_ms}ms</span></div>
        ${r.stdout ? `<pre class="mono tiny" style="white-space:pre-wrap;color:var(--ink-2)">${esc(r.stdout)}</pre>` : ''}
        ${r.stderr ? `<pre class="mono tiny" style="white-space:pre-wrap;color:var(--red)">${esc(r.stderr)}</pre>` : ''}</div>`;
    } catch (e) { toast(e.message, 'err'); }
    b.disabled = false; b.innerHTML = I.play + ' Run';
  }

  async function saveCanvas() {
    if (!C.nodes.length) return toast('Nothing to save', 'err');
    try {
      await POST('/saved', {
        item_type: 'canvas',
        title: `Canvas · ${C.nodes.length} shapes`,
        payload: {
          nodes: C.nodes.map(n => ({ id: n.id, type: n.type, label: n.label, x: n.x, y: n.y })),
          connections: C.conns.map(c => ({ fromNodeId: c.from, toNodeId: c.to })),
          generated_code: $('#cvCode').value,
        },
      });
      toast('Saved to your profile', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }

  function templateModal() {
    const T = {
      'if / else': { n: [['start', 'START', 0, 0], ['decision', 'x > 0', 0, 130], ['process', 'print("Positive")', -150, 280], ['process', 'print("Negative")', 150, 280], ['end', 'END', 0, 420]],
        c: [[0, 'bottom', 1, 'top'], [1, 'bottom', 2, 'top'], [1, 'right', 3, 'top'], [2, 'bottom', 4, 'top'], [3, 'bottom', 4, 'top']] },
      'for loop': { n: [['start', 'START', 0, 0], ['process', 'total = 0', 0, 120], ['decision', 'for i in range(5)', 0, 250], ['process', 'total += i', -140, 400], ['process', 'print(total)', 160, 400], ['end', 'END', 160, 520]],
        c: [[0, 'bottom', 1, 'top'], [1, 'bottom', 2, 'top'], [2, 'bottom', 3, 'top'], [2, 'right', 4, 'top'], [4, 'bottom', 5, 'top']] },
      'fibonacci': { n: [['start', 'START', 0, 0], ['process', 'n = 10', 0, 110], ['process', 'a, b = 0, 1', 0, 220], ['decision', 'for i in range(n)', 0, 340], ['process', 'a, b = b, a + b', -160, 490], ['process', 'print(a)', 170, 490], ['end', 'END', 170, 610]],
        c: [[0, 'bottom', 1, 'top'], [1, 'bottom', 2, 'top'], [2, 'bottom', 3, 'top'], [3, 'bottom', 4, 'top'], [3, 'right', 5, 'top'], [5, 'bottom', 6, 'top']] },
    };
    const m = modal(`<h3>Start from a template</h3>
      <div class="tiny muted" style="margin-bottom:16px">These use valid Python labels, so no AI call is needed</div>
      ${Object.keys(T).map(k => `<button class="list-item" data-t="${k}" style="width:100%;text-align:left">
        <div class="item-icon" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.canvas}</div>
        <div style="flex:1"><div style="font-weight:600;font-size:14px">${k}</div>
        <div class="tiny muted">${T[k].n.length} shapes</div></div></button>`).join('')}
      <button class="btn btn-ghost" style="width:100%;margin-top:10px"
        onclick="this.closest('.modal-bg').remove()">Cancel</button>`);
    $$('[data-t]', m).forEach(b => b.onclick = () => {
      const t = T[b.dataset.t], st = $('#stage');
      const cx = st.scrollLeft + st.clientWidth / 2, cy = st.scrollTop + 90;
      C.nodes = t.n.map(([type, label, dx, dy], i) => ({ id: 't' + i, type, label, x: cx + dx, y: cy + dy }));
      C.conns = t.c.map(([a, ap, z, zp]) => ({ from: 't' + a, fromPort: ap, to: 't' + z, toPort: zp }));
      C.badges = []; C.usedLlm = false; C.stale = true;
      m.remove(); draw(); generate();
    });
  }
}

/* ═══════════════ AI TUTOR CHAT ═══════════════ */
const mdLite = t => esc(t)
  .replace(/```(\w*)\n([\s\S]*?)```/g, (_, l, c) => `<pre><code>${c.replace(/\n$/, '')}</code></pre>`)
  .replace(/`([^`\n]+)`/g, '<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
  .replace(/\n/g, '<br>');

// Raw (un-escaped) code-block extraction — used to feed the editor, separate
// from mdLite's escaped HTML rendering above. Deliberately lenient: matches
// ```lang\ncode``` AND ```code``` (no language tag) AND cases with no
// trailing newline before the closing fence, since different models format
// fences slightly differently and a missed match means the button silently
// never appears.
function extractCodeBlocks(rawText) {
  if (!rawText) return [];
  const blocks = [];
  const re = /```([A-Za-z0-9_+-]*)\s*\n?([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(rawText)) !== null) {
    const code = m[2].replace(/\n$/, '').trim();
    if (code.length > 0) blocks.push({ lang: m[1] || '', code });
  }
  return blocks;
}

function viewChat() {
  const K = S.chat;
  K.roomId = S.params.id || null;
  shell('AI Tutor', 'Asks you questions — never hands over the answer', `
    <div class="chat-shell">
      <div class="chat-scroll" id="chatScroll"><div class="chat-inner" id="chatInner"></div></div>
      <div class="chat-bar"><div class="chat-bar-inner">
        <button class="btn btn-ghost" id="chatSaveBtn" title="Save this chat"
          style="border-radius:50%;width:42px;height:42px;padding:0;flex-shrink:0">${I.book}</button>
        <textarea id="chatInput" rows="1" placeholder="Ask about a concept, or paste code you're stuck on…"></textarea>
        <button class="btn" id="chatSend" style="border-radius:50%;width:42px;height:42px;padding:0">${I.send}</button>
      </div></div>
    </div>`, { bare: true });

  const inner = $('#chatInner'), scroll = $('#chatScroll'), inp = $('#chatInput');
  const paint = () => {
    inner.innerHTML = K.msgs.length ? K.msgs.map((m, idx) => `
      <div class="msg ${m.role === 'user' ? 'me' : ''}">
        <div class="msg-av ${m.role === 'user' ? 'usr' : 'ai'}">${m.role === 'user' ? esc(initials(S.user?.name)) : 'AI'}</div>
        <div class="bubble ${m.role === 'user' ? 'me' : 'ai'}">${m.role === 'user' ? esc(m.text) : mdLite(m.text)}
          ${m.role !== 'user' && extractCodeBlocks(m.text).length ? `
            <div style="margin-top:8px">
              <button class="btn btn-soft btn-sm" data-insert-idx="${idx}">${I.code} Insert into editor</button>
            </div>` : ''}
        </div>
      </div>`).join('') + (K.busy ? `<div class="msg"><div class="msg-av ai">AI</div>
        <div class="bubble ai" style="padding:0"><div class="typing"><span></span><span></span><span></span></div></div></div>` : '')
      : `<div class="empty">${I.chat}<h3>Ask me anything</h3>
        <div class="tiny" style="max-width:340px;margin:0 auto">
        I'll give you hints and questions to think through — not finished code. That's on purpose.</div>
        <div class="chips" style="justify-content:center;margin-top:18px">
        ${['What is a binary search tree?', 'Why is my recursion overflowing?', 'Explain time complexity']
          .map(q => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div></div>`;
    $$('[data-q]', inner).forEach(b => b.onclick = () => { inp.value = b.dataset.q; send(); });
    $$('[data-insert-idx]', inner).forEach(b => b.onclick = () => {
      const msg = K.msgs[+b.dataset.insertIdx];
      const blocks = extractCodeBlocks(msg?.text || '');
      if (!blocks.length) return;
      S.editor.code = blocks[0].code;
      if (blocks[0].lang) S.editor.lang = blocks[0].lang;
      toast('Code inserted into editor', 'ok');
      go('#/editor');
    });
    scroll.scrollTop = scroll.scrollHeight;
  };

  async function send() {
    const t = inp.value.trim();
    if (!t || K.busy) return;
    K.msgs.push({ role: 'user', text: t }); inp.value = ''; inp.style.height = 'auto';
    K.busy = true; paint();
    try {
      const r = await POST('/agent/message', { message: t, ...(K.roomId ? { room_id: K.roomId } : {}) });
      const d = r.data || {};
      let reply = d.response || d.summary || '';
      if (r.intent === 'progress' && d.total_submissions !== undefined) {
        reply = `**Your progress**\n\n${d.summary || ''}\n\nSubmissions: ${d.total_submissions} · Success rate: ${d.success_rate}%`;
      }
      if (r.intent === 'interview') reply = 'Mock interviews run in their own screen — open **Mock Interview** from the sidebar and pick a topic.';
      if (r.intent === 'company_prep') reply = `Company-specific prep runs in its own screen — open **Mock Interview** from the sidebar and enter "${d.company_guess || 'the company name'}" in the company field.`;
      if (!reply) reply = 'I could not form an answer for that. Try rephrasing?';
      K.msgs.push({ role: 'ai', text: reply });
    } catch (e) { K.msgs.push({ role: 'ai', text: 'Something went wrong: ' + e.message }); }
    K.busy = false; paint();
  }

  $('#chatSend').onclick = send;
  $('#chatSaveBtn').onclick = async () => {
    if (!K.msgs.length) { toast('Nothing to save yet', 'err'); return; }
    const btn = $('#chatSaveBtn'); btn.disabled = true;
    try {
      const firstUserMsg = K.msgs.find(m => m.role === 'user')?.text || 'Chat';
      await POST('/saved', {
        item_type: 'tutor_chat',
        title: firstUserMsg.slice(0, 60) + (firstUserMsg.length > 60 ? '…' : ''),
        payload: { messages: K.msgs },
      });
      toast('Chat saved', 'ok');
    } catch (e) { toast(e.message, 'err'); }
    btn.disabled = false;
  };
  inp.addEventListener('input', () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 140) + 'px'; });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  paint(); inp.focus();
}

/* ═══════════════ PROCTORING ENGINE ═══════════════ */
const Proctor = {
  stream: null, videoEl: null, checkTimer: null, modelsReady: false,
  strikes: 0, maxStrikes: 2, noFaceSince: null, tooCloseSince: null, active: false,
  onWarn: null, onEnd: null,

  async loadModels() {
    if (this.modelsReady) return;
    await new Promise((resolve, reject) => {
      if (window.faceapi) return resolve();
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js';
      s.onload = resolve; s.onerror = () => reject(new Error('Could not load the face-detection engine'));
      document.head.appendChild(s);
    });
    const MODEL_URL = 'https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    this.modelsReady = true;
  },

  async start(videoEl, { onWarn, onEnd }, existingStream) {
    this.videoEl = videoEl; this.onWarn = onWarn; this.onEnd = onEnd;
    this.strikes = 0; this.noFaceSince = null; this.tooCloseSince = null;
    this.stream = existingStream || await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 }, audio: true });
    videoEl.srcObject = this.stream;
    await videoEl.play();
    this.active = true;
    document.addEventListener('visibilitychange', this._onVis);
    try {
      await this.loadModels();
      this.checkTimer = setInterval(() => this._checkFace(), 1000);
    } catch (e) {
      console.warn('Face tracking unavailable:', e);
      this._setFaceStatus('error', 'Face tracking unavailable');
    }
  },

  _onVis: () => {
    if (!Proctor.active || document.hidden !== true) return;
    Proctor._strike('tab', 'You switched away from the interview tab.');
  },

  async _checkFace() {
    if (!this.active || !this.videoEl || this.videoEl.readyState < 2) return;
    let det;
    try {
      det = await faceapi.detectSingleFace(this.videoEl, new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.5 }));
    } catch (e) {
      console.warn('Face check error:', e);
      det = undefined;
    }
    this._drawBox(det);

    if (det) {
      const vw = this.videoEl.videoWidth || 1, vh = this.videoEl.videoHeight || 1;
      const areaRatio = (det.box.width * det.box.height) / (vw * vh);
      if (areaRatio > 0.6) {
        this.noFaceSince = null;
        this._setFaceStatus('warn', "Too close — move back");
        if (!this.tooCloseSince) { this.tooCloseSince = Date.now(); return; }
        if (Date.now() - this.tooCloseSince > 2800) {
          this.tooCloseSince = null;
          this._strike('close', "You're too close to the camera.");
        }
        return;
      }
      this.tooCloseSince = null; this.noFaceSince = null;
      this._setFaceStatus('ok', 'Face detected');
      return;
    }

    this.tooCloseSince = null;
    this._setFaceStatus('warn', 'Center face in frame');
    if (!this.noFaceSince) { this.noFaceSince = Date.now(); return; }
    if (Date.now() - this.noFaceSince > 2800) {
      this.noFaceSince = null;
      this._strike('face', "You're not visible on camera.");
    }
  },

  _drawBox(det) {
    const canvas = document.getElementById('ivFaceCanvas');
    if (!canvas || !this.videoEl) return;
    const vw = this.videoEl.videoWidth, vh = this.videoEl.videoHeight;
    if (!vw || !vh) return;
    if (canvas.width !== vw) canvas.width = vw;
    if (canvas.height !== vh) canvas.height = vh;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, vw, vh);
    if (det) {
      const { x, y, width, height } = det.box;
      ctx.strokeStyle = '#22C55E'; ctx.lineWidth = Math.max(3, vw * 0.008);
      const r = 8;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, y, width, height, r) : ctx.strokeRect(x, y, width, height);
      ctx.stroke();
    }
  },

  _setFaceStatus(kind, text) {
    const el = document.getElementById('faceStatus');
    if (!el) return;
    el.textContent = text;
    el.className = 'iv-proctor-pill ' + (kind === 'ok' ? 'ok' : 'warn');
  },

  _strike(kind, msg) {
    if (!this.active) return;
    this.strikes++;
    if (this.strikes >= this.maxStrikes) { this.active = false; this.onEnd?.(kind, msg); }
    else this.onWarn?.(kind, msg, this.strikes, this.maxStrikes);
  },

  stop() {
    this.active = false;
    document.removeEventListener('visibilitychange', this._onVis);
    clearInterval(this.checkTimer); this.checkTimer = null;
    this.stream?.getTracks().forEach(t => t.stop()); this.stream = null;
    if (this.videoEl) this.videoEl.srcObject = null;
    const canvas = document.getElementById('ivFaceCanvas');
    if (canvas) canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
  },
};

/* ─────────── Manual Push-to-Talk Speech recognition ─────────── */
const SpeechIn = {
  rec: null,
  supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
  listening: false,
  accumulatedText: '',
  onInterimCb: null,
  _activeWanted: false,
  _lastInterim: '',

  start(onInterim) {
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Ctor) return;
    this.accumulatedText = '';
    this._lastInterim = '';
    this.onInterimCb = onInterim;
    this._activeWanted = true;
    this._initAndRun();
  },

  _initAndRun() {
    if (!this._activeWanted) return;
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    try {
      if (this.rec) { this.rec.onend = null; this.rec.onerror = null; this.rec.onresult = null; this.rec.abort(); }
    } catch {}

    const r = new Ctor();
    r.lang = 'en-US';
    r.interimResults = true;
    r.continuous = true;

    r.onresult = e => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) {
          this.accumulatedText += (this.accumulatedText ? ' ' : '') + t.trim();
          this._lastInterim = '';
        } else {
          interim += t;
        }
      }
      // Keep the newest interim around. If Chrome tears the engine down
      // before promoting it to final, we'd otherwise lose the last phrase.
      if (interim) this._lastInterim = interim.trim();
      this.onInterimCb?.(this._full());
    };

    r.onerror = e => {
      // 'no-speech'/'aborted' are routine with continuous:true — never fatal.
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      console.warn('SpeechRecognition error:', e.error);
    };

    r.onend = () => {
      // Chrome ends the session on its own (silence timeout / ~60s cap) even
      // with continuous:true. Reusing the dead recognizer throws
      // InvalidStateError, so we always build a fresh one. Text accumulated
      // so far is preserved across the respawn.
      this.listening = false;
      if (this._activeWanted) {
        setTimeout(() => { if (this._activeWanted) this._initAndRun(); }, 150);
      }
    };

    this.rec = r;
    try {
      r.start();
      this.listening = true;
    } catch (err) {
      console.warn('Recognition start failed:', err);
      // Retry once shortly — the engine is often just still tearing down.
      if (this._activeWanted) setTimeout(() => this._initAndRun(), 250);
    }
  },

  _full() {
    return (this.accumulatedText + (this._lastInterim ? ' ' + this._lastInterim : '')).trim();
  },

  stop() {
    this._activeWanted = false;
    this.listening = false;
    try {
      if (this.rec) { this.rec.onend = null; this.rec.onerror = null; this.rec.stop(); }
    } catch {}
    // Include any un-promoted interim so the tail of the answer isn't dropped.
    const text = this._full();
    this.accumulatedText = '';
    this._lastInterim = '';
    return text;
  },
};

const SpeechOut = {
  supported: 'speechSynthesis' in window,
  speak(text, onDone) {
    if (!this.supported || document.hidden) { onDone?.(); return; }
    speechSynthesis.cancel();
    const clean = text
      .replace(/```[\s\S]*?```/g, ' code block ')
      .replace(/`([^`]*)`/g, '$1')
      .replace(/[*_#>~]/g, '')
      .replace(/\.{2,}/g, ' ')
      .replace(/^[\s]*[-•]\s+/gm, '')
      .replace(/^[\s]*\d+\.\s+/gm, '')
      .replace(/\s{2,}/g, ' ')
      .trim();
    if (!clean || !/[a-zA-Z0-9]/.test(clean)) return onDone?.();
    const u = new SpeechSynthesisUtterance(clean);
    u.rate = 1; u.pitch = 1;
    u.onend = () => onDone?.();
    u.onerror = () => onDone?.();
    speechSynthesis.speak(u);
  },
  stop() { if (this.supported) speechSynthesis.cancel(); },
};

const TOPICS = [['arrays', 'Arrays'], ['strings', 'Strings'], ['trees', 'Trees'],
  ['graphs', 'Graphs'], ['dp', 'Dynamic Programming'], ['linked_list', 'Linked Lists']];

const ROUND_TYPES = [
  ['technical_l1', 'Technical L1', 'DSA fundamentals, easier warm-up round'],
  ['technical_l2', 'Technical L2', 'Deeper DSA, follow-up on complexity & optimization'],
  ['technical_l3', 'Technical L3', 'Senior/advanced technical round'],
  ['behavioral', 'Behavioral', 'Past experience, teamwork, conflict handling'],
  ['hr', 'HR / Screening', 'Fit, expectations, culture questions'],
];

/* ═══════════════ MOCK INTERVIEW VIEW ═══════════════ */
function viewInterview() {
  const V = S.iv;
  const body = V.stage === 'pick' ? pickHtml()
    : V.stage === 'precheck' ? precheckHtml()
    : V.stage === 'live' ? liveHorizontalHtml()
    : fbHtml();
  shell('Mock Interview', 'A proctored, voice-based interview round', body,
    { bare: V.stage === 'live', actions: V.stage !== 'pick' ? `<button class="btn btn-ghost btn-sm" id="ivReset">Start over</button>` : '' });

  if ($('#ivReset')) $('#ivReset').onclick = () => {
    Proctor.stop(); SpeechOut.stop(); SpeechIn.stop();
    V._precheckStream?.getTracks().forEach(t => t.stop());
    Object.assign(V, { stage: 'pick', sid: null, msgs: [], fb: null, busy: false, endNote: null,
      recording: false, _precheckMounted: false, _liveMounted: false, _precheckStream: null,
      company: null, adaptiveHint: null, _adaptiveFetched: false, _diagnosticFetched: false, roundType: 'technical_l1' });
    viewInterview();
  };

  if (V.stage === 'pick') {
    $$('[data-round]').forEach(b => b.onclick = () => {
      V.roundType = b.dataset.round;
      if (!b.dataset.round.startsWith('technical')) V.topic = null; // behavioral/hr don't use DSA topics
      viewInterview();
    });
    $$('[data-topic]').forEach(b => b.onclick = () => { V.topic = b.dataset.topic; viewInterview(); });
    $$('[data-diff]').forEach(b => b.onclick = () => { V.diff = b.dataset.diff; viewInterview(); });
    if ($('#ivCompany')) $('#ivCompany').oninput = e => { V.company = e.target.value.trim(); };
    $('#ivStart').onclick = () => { V.stage = 'precheck'; V._precheckMounted = false; viewInterview(); };

    // Adaptive suggestion — fetch once, non-blocking, shows a hint but never forces a pick
    if (!V._adaptiveFetched) {
      V._adaptiveFetched = true;
      GET('/agent/interview/adaptive-pick').then(r => {
        if (r?.topic && !V.topic) {
          V.adaptiveHint = r.reason || `Suggested: ${r.topic}`;
          viewInterview();
        }
      }).catch(() => {}); // best-effort — silent fail, user can still pick manually
    }
  }

  if (V.stage === 'precheck') {
    if (!V._precheckMounted) { V._precheckMounted = true; initPrecheck(); }
    $('#ivReady').onclick = async () => {
      const b = $('#ivReady'); b.disabled = true; b.innerHTML = '<span class="spinner"></span> Starting';
      try {
        const r = await POST('/agent/interview/start', { topic: V.topic, difficulty: V.diff, company: V.company || null, round_type: V.roundType });
        V.sid = r.session_id; V.msgs = [{ role: 'ai', text: r.question }];
        V.topic = r.topic || V.topic; // server may resolve topic when only company was given
        V.stage = 'live'; V._liveMounted = false;
        viewInterview();
      } catch (e) { toast(e.message, 'err'); b.disabled = false; b.textContent = "I'm ready — begin"; }
    };
  }

  if (V.stage === 'live' && !V._liveMounted) { V._liveMounted = true; mountLive(); }

  if (V.stage === 'fb' && $('#ivAgain')) {
    $('#ivAgain').onclick = () => {
      Proctor.stop(); SpeechOut.stop(); SpeechIn.stop();
      V._precheckStream?.getTracks().forEach(t => t.stop());
      Object.assign(V, { stage: 'pick', sid: null, msgs: [], fb: null, busy: false,
        endNote: null, recording: false, _precheckMounted: false, _liveMounted: false,
        _precheckStream: null, company: null, adaptiveHint: null, _adaptiveFetched: false,
        _diagnosticFetched: false, roundType: 'technical_l1' });
      viewInterview();
    };
  }

  if (V.stage === 'fb' && V.fb && !V._diagnosticFetched) {
    V._diagnosticFetched = true;
    GET('/agent/progress/diagnostic').then(r => {
      const el = $('#fbDiagnostic');
      if (!el || !r) return;
      el.innerHTML = `
        <section class="fb-card" style="margin-top:18px">
          <header class="fb-card-head"><span class="fb-dot fb-dot-cyan"></span><h4>Your overall standing</h4></header>
          <p class="fb-body" style="margin-bottom:6px"><b>Strong:</b> ${esc(r.strong_summary || '—')}</p>
          <p class="fb-body" style="margin-bottom:6px"><b>Needs work:</b> ${esc(r.weak_summary || '—')}</p>
          <p class="fb-body"><b>Next step:</b> ${esc(r.recommendation || '—')}</p>
        </section>`;
    }).catch(() => {}); // best-effort — silent fail, feedback screen still works without it
  }

  if (V.stage === 'fb' && $('#ivSave')) {
    $('#ivSave').onclick = async () => {
      const b = $('#ivSave'); b.disabled = true;
      try {
        await POST('/saved', { item_type: 'interview',
          title: `${TOPICS.find(t => t[0] === V.topic)?.[1] || V.topic} · ${V.diff}`,
          payload: { topic: V.topic, difficulty: V.diff, question: V.msgs[0]?.text,
            transcript: V.msgs.filter(m => m.role !== 'system').map(m => ({ role: m.role === 'user' ? 'student' : 'interviewer', text: m.text })),
            feedback: V.fb } });
        b.innerHTML = I.check + ' Saved'; toast('Saved to your profile', 'ok');
      } catch (e) { toast(e.message, 'err'); b.disabled = false; }
    };
  }

  async function initPrecheck() {
    const video = $('#pcVideo'), overlay = $('#pcOverlay'), btn = $('#ivReady');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 }, audio: true });
      V._precheckStream = stream;
      video.srcObject = stream; await video.play();
      overlay.style.display = 'none';
      btn.disabled = false; btn.textContent = "I'm ready — begin";
      Proctor.loadModels().catch(() => { });
    } catch (e) {
      overlay.innerHTML = `${I.alert}<div style="margin-top:8px">Camera and microphone access is required for a proctored interview.</div>`;
      btn.textContent = 'Camera access denied';
    }
  }

  async function mountLive() {
    const video = $('#ivVideo');
    wireLiveControls();
    updateLiveCards();

    try {
      await Proctor.start(video, {
        onWarn: (kind, msg, n, max) => {
          SpeechOut.speak(msg);
          updateStrikes(n, max);
          toast(msg, 'err');
        },
        onEnd: (kind, msg) => {
          V.endNote = 'Ended early — ' + msg;
          SpeechOut.speak('This interview has ended due to a proctoring violation.');
          endIv();
        },
      }, V._precheckStream);
    } catch (e) {
      toast('Lost camera/mic access: ' + e.message, 'err');
    }

    setAiSpeaking(true);
    SpeechOut.speak(V.msgs[0]?.text || '', () => setAiSpeaking(false));
  }

  function wireLiveControls() {
    const btn = $('#liveRecBtn');
    const liveTextEl = $('#liveSpeechText');

    const sec = $('#historySection'), tog = $('#historyToggle');
    if (tog && sec) tog.onclick = () => sec.classList.toggle('open');

    // V.recording is OUR source of truth for the button, deliberately NOT
    // SpeechIn.listening. Chrome can silently kill the recognition engine at
    // any moment; when that happened the button still said "Stop & Submit"
    // but SpeechIn.listening was already false, so the next tap fell into
    // the START branch, wiped accumulatedText, and the answer was never
    // sent — the interview just froze. Now only a real user tap flips this.
    const setRecUI = on => {
      V.recording = on;
      if (!btn) return;
      btn.classList.toggle('recording', on);
      btn.innerHTML = on ? `${I.stop} Stop & Submit Answer` : `${I.mic} Tap to Speak Answer`;
      $('#userCard')?.classList.toggle('user-active', on);
    };

    const setText = (t, isPlaceholder) => {
      if (!liveTextEl) return;
      liveTextEl.textContent = t;
      liveTextEl.classList.toggle('placeholder', !!isPlaceholder);
    };

    if (!btn) return;

    btn.onclick = () => {
      if (V.busy) return;

      // ── STOP & SUBMIT ──
      if (V.recording) {
        setRecUI(false);
        const finalTxt = (SpeechIn.stop() || '').trim();
        if (finalTxt) {
          setText(`"${finalTxt}"`, false);
          sendAnswer(finalTxt);
        } else {
          setText('No voice input detected. Tap the mic and try again.', true);
        }
        return;
      }

      // ── START ──
      SpeechOut.stop();
      setAiSpeaking(false);
      setRecUI(true);
      setText('Listening… speak freely, then tap to submit.', false);

      SpeechIn.start(liveTxt => {
        if (liveTxt) setText(`"${liveTxt}"`, false);
      });
    };
  }

  function setAiSpeaking(isSpeaking) {
    V.aiSpeaking = isSpeaking;
    const aiCard = $('#aiCard');
    const aiStatus = $('#aiStatusLbl');
    if (isSpeaking) {
      aiCard?.classList.add('ai-active');
      if (aiStatus) aiStatus.textContent = 'Speaking...';
    } else {
      aiCard?.classList.remove('ai-active');
      if (aiStatus) aiStatus.textContent = 'Ready & Listening';
    }
  }

  function updateStrikes(n, max) {
    const b = $('#ivStrikes'); if (!b) return;
    b.style.display = 'inline-flex'; b.className = 'pill pill-amber';
    b.innerHTML = `${I.alert} Warning ${n}/${max}`;
  }

  function updateLiveCards() {
    const qBox = $('#currentQuestionText');
    const logBox = $('#historyLog');
    const latestAiMsg = [...V.msgs].reverse().find(m => m.role === 'ai')?.text || '';

    if (qBox && latestAiMsg && qBox.dataset.txt !== latestAiMsg) {
      qBox.dataset.txt = latestAiMsg;
      qBox.innerHTML = mdLite(latestAiMsg);
      // replay the entrance animation on every new interviewer turn
      qBox.classList.remove('q-enter');
      void qBox.offsetWidth;
      qBox.classList.add('q-enter');
    }

    if (logBox) {
      logBox.innerHTML = V.msgs.map(m => `
        <div style="color:${m.role === 'ai' ? '#5FE3F0' : '#C3B2FD'}">
          <b>${m.role === 'ai' ? 'Interviewer' : 'You'}:</b> ${esc(m.text)}
        </div>
      `).join('');
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  async function sendAnswer(text) {
    if (V.busy) return;
    V.msgs.push({ role: 'user', text });
    updateLiveCards();
    V.busy = true;
    const aiStatusEl = $('#aiStatusLbl');
    if (aiStatusEl) aiStatusEl.textContent = 'Thinking…';

    const liveTextEl = $('#liveSpeechText');
    if (liveTextEl) {
      liveTextEl.classList.remove('placeholder');
      liveTextEl.innerHTML = `<span class="iv-thinking"><i></i><i></i><i></i></span> <span style="margin-left:6px">Analyzing your answer…</span>`;
    }

    try {
      const r = await POST('/agent/interview/continue', { session_id: V.sid, message: text });
      const reply = (r && r.interviewer_response || '').trim();
      if (!reply) throw new Error('Interviewer sent an empty reply — try again.');

      V.msgs.push({ role: 'ai', text: reply });
      updateLiveCards();

      if (liveTextEl) {
        liveTextEl.textContent = 'Tap the button below to speak your next answer…';
        liveTextEl.classList.add('placeholder');
      }

      setAiSpeaking(true);
      SpeechOut.speak(reply, () => setAiSpeaking(false));

      if (r && r.should_end) {
        V.endNote = null;
        setTimeout(() => endIv(), 1000);
      }
    } catch (e) {
      toast(e.message || 'Could not reach the interviewer', 'err');
      if (liveTextEl) {
        liveTextEl.textContent = 'Could not reach the interviewer. Tap the mic to try again.';
        liveTextEl.classList.add('placeholder');
      }
    } finally {
      // Always release the lock. Previously an unexpected throw (or a
      // response missing interviewer_response) could leave V.busy stuck at
      // true, which made every later mic tap a no-op — the frozen interview.
      V.busy = false;
      V.recording = false;
      setAiSpeaking(false);
      const b = $('#liveRecBtn');
      if (b) {
        b.classList.remove('recording');
        b.innerHTML = `${I.mic} Tap to Speak Answer`;
      }
      $('#userCard')?.classList.remove('user-active');
      const st = $('#aiStatusLbl');
      if (st && st.textContent === 'Thinking…') st.textContent = 'Ready & Listening';
    }
  }

  async function endIv() {
    Proctor.stop(); SpeechOut.stop(); SpeechIn.stop();
    V.stage = 'fb'; V.fb = null; V._liveMounted = false;
    viewInterview();
    try { V.fb = await POST('/agent/interview/feedback', { session_id: V.sid }); }
    catch (e) { toast(e.message, 'err'); }
    viewInterview();
  }

  function pickHtml() {
    const isTechnical = (V.roundType || 'technical_l1').startsWith('technical');
    return `<div class="hero" style="margin-bottom:22px">
        <div class="row" style="gap:8px;margin-bottom:8px">
          <span class="pill" style="background:rgba(255,255,255,.18);color:#fff;gap:6px">${I.shield} Proctored round</span>
        </div>
        <div style="font-size:19px;font-weight:800;margin-bottom:4px">Practice a real interview round</div>
        <div style="opacity:.92;font-size:13.5px;max-width:520px">A voice conversation with an AI interviewer — it asks a question, probes your approach out loud, and gives you an honest verdict at the end. Camera and mic stay on throughout.</div>
      </div>
      <div class="section-title">Round type</div>
      <div class="grid g3" style="margin-bottom:22px">
        ${ROUND_TYPES.map(([k, l, desc]) => `<button class="tool" data-round="${k}"
          style="text-align:left;${V.roundType === k ? 'border-color:var(--cyan);background:var(--cyan-soft)' : ''}">
          <div class="tool-ic" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.mic}</div>
          <h4>${l}</h4>
          <div class="tiny muted" style="margin-top:2px">${desc}</div></button>`).join('')}
      </div>
      ${isTechnical ? `
      <div class="section-title">Pick a topic</div>
      <div class="grid g3" style="margin-bottom:22px">
        ${TOPICS.map(([k, l]) => `<button class="tool" data-topic="${k}"
          style="text-align:left;${V.topic === k ? 'border-color:var(--cyan);background:var(--cyan-soft)' : ''}">
          <div class="tool-ic" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.code}</div>
          <h4>${l}</h4></button>`).join('')}
      </div>` : ''}
      <div class="section-title">Difficulty</div>
      <div class="chips" style="margin-bottom:26px">
        ${['easy', 'medium', 'hard'].map(d => `<button class="chip ${V.diff === d ? 'on' : ''}" data-diff="${d}">
          ${d[0].toUpperCase() + d.slice(1)}</button>`).join('')}
      </div>
      <div class="section-title">Practicing for a specific company? (optional)</div>
      <input id="ivCompany" type="text" placeholder="e.g. Cognizant, ZS Associates, TCS"
        value="${esc(V.company || '')}"
        style="width:100%;max-width:320px;margin-bottom:10px;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:var(--bg-soft)" />
      <div class="tiny muted" style="margin-bottom:22px;max-width:320px">
        We'll ground the question in patterns reported by past candidates at that company.
      </div>
      ${V.adaptiveHint ? `<div class="tiny" style="margin-bottom:14px;color:var(--cyan-dark)">${esc(V.adaptiveHint)}</div>` : ''}
      <button class="btn btn-lg" id="ivStart" style="width:100%;max-width:320px" ${(isTechnical ? (V.topic || V.company) : V.roundType) ? '' : 'disabled'}>
        ${(isTechnical ? (V.topic || V.company) : V.roundType) ? 'Continue' : 'Pick a topic first'}</button>`;
  }

  function precheckHtml() {
    return `<div class="pc-wrap">
      <div class="pc-video-box">
        <video id="pcVideo" autoplay playsinline muted></video>
        <div class="pc-video-overlay" id="pcOverlay"><span class="spinner"></span><div style="margin-top:8px">Requesting camera…</div></div>
      </div>
      <div class="pc-info">
        <div class="section-title">${I.shield} Before you begin</div>
        <div class="pc-rule">${I.camera}<span>Your camera stays on and your face must stay visible the whole time.</span></div>
        <div class="pc-rule">${I.eye}<span>Don't switch tabs or minimize the window during the round.</span></div>
        <div class="pc-rule">${I.alert}<span>Two warnings — camera or tab — and the interview ends automatically.</span></div>
        <div class="pc-rule">${I.mic}<span>You'll answer out loud. The interviewer listens and replies by voice too.</span></div>
        <div class="tiny muted" style="margin-top:12px">Video and audio are processed only in your browser — nothing is recorded or uploaded anywhere.</div>
        <button class="btn btn-lg" id="ivReady" style="width:100%;margin-top:20px" disabled>Preparing camera…</button>
      </div>
    </div>`;
  }

  function liveHorizontalHtml() {
    return `<div class="iv-stage-layout">
      <div class="iv-stage-header">
        <div class="row" style="gap:10px">
          <span class="pill pill-cyan">${TOPICS.find(t => t[0] === V.topic)?.[1] || V.topic} · ${V.diff}</span>
          <span class="pill pill-gray" id="ivStrikes" style="display:none"></span>
        </div>
        <span class="pill pill-green" style="gap:6px">${I.shield} Proctored Active</span>
      </div>

      <div class="iv-cards-container">
        <!-- LEFT HORIZONTAL CARD: AI INTERVIEWER -->
        <div class="iv-card" id="aiCard">
          <div class="iv-card-top">
            <span class="iv-badge-tag iv-badge-ai">AI Interviewer</span>
            <span class="tiny" id="aiStatusLbl" style="color:#7CA4B5">Ready</span>
          </div>

          <div class="iv-ai-body">
            <div class="iv-avatar-wave-row">
              <div class="iv-interviewer-avatar">
                <span class="iv-interviewer-pulse"></span>
                ${I.volume}
              </div>
              <div style="flex:1">
                <div style="font-weight:700;font-size:15px;margin-bottom:4px">Technical Interviewer</div>
                <div class="iv-wave-bars">
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                  <div class="iv-wave-bar"></div>
                </div>
              </div>
            </div>

            <div class="iv-current-question-box" id="currentQuestionText">
              <span class="spinner"></span> Loading problem...
            </div>

            <div class="iv-history-section" id="historySection">
              <div class="iv-history-toggle" id="historyToggle">
                ${I.chat}<span>Conversation log</span>
                <svg class="iv-history-chev" fill="none" stroke="currentColor" stroke-width="2.4" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>
              </div>
              <div class="iv-history-log" id="historyLog"></div>
            </div>
          </div>
        </div>

        <!-- RIGHT HORIZONTAL CARD: CANDIDATE / USER -->
        <div class="iv-card" id="userCard">
          <div class="iv-card-top">
            <span class="iv-badge-tag iv-badge-user">You (Candidate)</span>
            <span class="tiny" style="color:#7CA4B5">Live Voice Input</span>
          </div>

          <div class="iv-user-body">
            <div class="iv-camera-preview">
              <video id="ivVideo" autoplay playsinline muted></video>
              <canvas id="ivFaceCanvas"></canvas>
              <div class="iv-proctor-pill" id="faceStatus">Tracking...</div>
            </div>

            <div class="iv-speech-display-box">
              <div class="iv-user-live-wave">
                <span class="iv-live-bar"></span>
                <span class="iv-live-bar"></span>
                <span class="iv-live-bar"></span>
                <span class="iv-live-bar"></span>
                <span class="iv-live-bar"></span>
              </div>
              <div class="iv-speech-text placeholder" id="liveSpeechText">
                Tap the button below and explain your approach...
              </div>
            </div>

            <div class="iv-action-row">
              <button class="iv-btn-rec" id="liveRecBtn">
                ${I.mic} Tap to Speak Answer
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  }

  function fbHtml() {
    if (!V.fb) return `<div class="fb-loading">
      <div class="fb-loading-ring"><span></span><span></span><span></span></div>
      <h3>Reviewing your interview…</h3>
      <p>Scoring your approach, complexity analysis and communication.</p>
    </div>`;

    const f = V.fb;
    const RATINGS = {
      'Strong Hire':   { cls: 'sh', pct: 100, note: 'Excellent round' },
      'Hire':          { cls: 'h',  pct: 78,  note: 'Solid performance' },
      'Borderline':    { cls: 'b',  pct: 52,  note: 'Nearly there' },
      'Needs Practice':{ cls: 'np', pct: 28,  note: 'Keep practising' },
    };
    const r = RATINGS[f.overall_rating] || { cls: 'np', pct: 20, note: 'Result' };
    const topicLbl = TOPICS.find(t => t[0] === V.topic)?.[1] || V.topic || '—';
    const turns = V.msgs.filter(m => m.role === 'user').length;

    const list = (title, arr, kind) => (arr && arr.length) ? `
      <section class="fb-card fb-${kind}">
        <header class="fb-card-head">
          <span class="fb-dot"></span>
          <h4>${title}</h4>
          <span class="fb-count">${arr.length}</span>
        </header>
        <ul class="fb-list">
          ${arr.map((x, i) => `<li style="animation-delay:${i * 70}ms"><span class="fb-tick">${kind === 'good' ? I.check : I.alert}</span><span>${esc(x)}</span></li>`).join('')}
        </ul>
      </section>` : '';

    return `
      ${V.endNote ? `<div class="iv-end-banner">${I.alert}<span>${esc(V.endNote)}</span></div>` : ''}

      <div class="fb-wrap">
        <div class="fb-hero fb-tone-${r.cls}">
          <div class="fb-hero-left">
            <div class="fb-verdict-label">Interviewer verdict</div>
            <div class="fb-verdict">${esc(f.overall_rating || '—')}</div>
            <div class="fb-verdict-note">${r.note}</div>
            <div class="fb-meta">
              <span class="fb-chip">${topicLbl}</span>
              <span class="fb-chip">${esc(V.diff || 'medium')}</span>
              <span class="fb-chip">${turns} answer${turns === 1 ? '' : 's'}</span>
            </div>
          </div>
          <div class="fb-gauge" style="--pct:${r.pct}">
            <svg viewBox="0 0 120 120">
              <circle class="fb-gauge-track" cx="60" cy="60" r="52"/>
              <circle class="fb-gauge-fill" cx="60" cy="60" r="52"/>
            </svg>
            <div class="fb-gauge-num"><b>${r.pct}</b><i>score</i></div>
          </div>
        </div>

        ${f.summary ? `<div class="fb-summary"><span class="fb-quote">"</span>${esc(f.summary)}</div>` : ''}

        <div class="fb-grid">
          ${list('Strengths', f.strengths, 'good')}
          ${list('Areas to improve', f.improvements, 'work')}
        </div>

        <div class="fb-grid">
          <section class="fb-card">
            <header class="fb-card-head"><span class="fb-dot fb-dot-cyan"></span><h4>Complexity understanding</h4></header>
            <p class="fb-body">${esc(f.complexity_understanding || '—')}</p>
          </section>
          <section class="fb-card">
            <header class="fb-card-head"><span class="fb-dot fb-dot-purple"></span><h4>Communication</h4></header>
            <p class="fb-body">${esc(f.communication || '—')}</p>
          </section>
        </div>

        <div id="fbDiagnostic"></div>

        <div class="fb-actions">
          <button class="btn btn-lg" id="ivSave">${I.save} Save this interview</button>
          <button class="btn btn-ghost btn-lg" id="ivAgain">Practice another round</button>
        </div>
      </div>`;
  }

}

/* ═══════════════ PROGRESS ═══════════════ */
async function viewProgress() {
  shell('Progress', 'Where you actually stand', `<div id="pg">${skelStats(3)}<div style="margin-top:14px">${skelRows(2)}</div></div>`);
  try {
    const d = await GET('/agent/progress');
    if (!d.total_submissions) {
      $('#pg').innerHTML = `<div class="empty">${I.chart}<h3>No activity yet</h3>
        <div class="tiny">Run some code and your progress will show up here</div>
        <a href="#/editor" class="btn btn-sm" style="margin-top:14px">Open editor</a></div>`;
      return;
    }
    const rate = d.success_rate ?? 0;
    const col = rate >= 70 ? 'var(--green)' : rate >= 40 ? 'var(--amber)' : 'var(--red)';
    const R = 54, C = 2 * Math.PI * R;
    const dash = (rate / 100) * C;
    const langs = Object.entries(d.languages || {});
    const days = d.most_active_days || [];

    $('#pg').innerHTML = `
      <div class="card prog-hero" style="margin-bottom:18px">
        <div class="prog-ring-wrap">
          <svg viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="${R}" fill="none" stroke="var(--surface-2)" stroke-width="10"/>
            <circle cx="60" cy="60" r="${R}" fill="none" stroke="${col}" stroke-width="10"
              stroke-linecap="round" stroke-dasharray="${dash} ${C}"/>
          </svg>
          <div class="prog-ring-label"><div class="num" style="color:${col}">${rate}%</div><div class="lbl">SUCCESS</div></div>
        </div>
        <div class="prog-side-stats">
          <div class="prog-side-row">
            <div class="prog-side-ic" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.check}</div>
            <div><div class="prog-side-val">${d.total_submissions}</div><div class="prog-side-lbl">Submissions in the last 30 days</div></div>
          </div>
          <div class="prog-side-row">
            <div class="prog-side-ic" style="background:var(--amber-soft);color:var(--amber)">${I.fire}</div>
            <div><div class="prog-side-val">${S.user?.streak ?? 0} days</div><div class="prog-side-lbl">Current streak</div></div>
          </div>
          <div class="prog-side-row">
            <div class="prog-side-ic" style="background:var(--purple-soft);color:var(--purple)">${I.bolt}</div>
            <div><div class="prog-side-val">${S.user?.xp ?? 0} XP</div><div class="prog-side-lbl">Total earned</div></div>
          </div>
        </div>
      </div>
      <div class="grid g2" style="margin-bottom:18px">
        <div class="card card-pad">
          <div class="section-title">${I.code} Languages practiced</div>
          ${langs.length ? langs.map(([k, v]) => `<div class="tag-row">
              <div class="tag-row-ic" style="background:var(--cyan-soft);color:var(--cyan-dark)">${I.code}</div>
              <div class="tag-row-name">${esc(k)}</div><div class="tag-row-count">${v} run${v === 1 ? '' : 's'}</div>
            </div>`).join('') : `<div class="tiny muted">Nothing yet</div>`}
        </div>
        <div class="card card-pad">
          <div class="section-title">${I.chart} Most active days</div>
          ${days.length ? days.map(x => `<div class="tag-row">
              <div class="tag-row-ic" style="background:var(--purple-soft);color:var(--purple)">${I.chart}</div>
              <div class="tag-row-name">${esc(x)}</div>
            </div>`).join('') : `<div class="tiny muted">Not enough data yet</div>`}
        </div>
      </div>
      <div class="card card-pad" style="background:linear-gradient(135deg,var(--cyan-soft),var(--purple-soft));border-color:var(--cyan)">
        <div class="section-title" style="color:var(--cyan-dark)">${I.spark} AI insight</div>
        <p style="font-size:14px;line-height:1.65;color:var(--ink-2)">${esc(d.summary || '')}</p>
        ${d.recommended_focus ? `<div class="card card-pad" style="margin-top:14px;padding:11px 14px;background:var(--surface)">
          <div class="row" style="gap:9px"><span class="pill pill-amber">Focus next</span>
          <span style="font-size:13.5px;font-weight:600">${esc(d.recommended_focus)}</span></div></div>` : ''}
      </div>`;
  } catch (e) { $('#pg').innerHTML = `<div class="empty"><h3>${esc(e.message)}</h3></div>`; }
}

/* ═══════════════ SAVED ═══════════════ */
const SAVED_META = {
  interview: ['Mock Interview', I.mic, 'var(--amber)', 'var(--amber-soft)'],
  canvas: ['Canvas', I.canvas, 'var(--cyan)', 'var(--cyan-soft)'],
  tutor_chat: ['AI Chat', I.chat, 'var(--purple)', 'var(--purple-soft)'],
  code_review: ['Code Review', I.spark, 'var(--green)', 'var(--green-soft)'],
  editor_code: ['Code Snippet', I.code, 'var(--cyan)', 'var(--cyan-soft)'],
};

async function viewSaved() {
  let filter = null;
  shell('Saved', 'Everything you kept for later', `
    <div class="chips" id="savedFilters" style="margin-bottom:16px">
      <button class="chip on" data-f="">All</button>
      ${Object.entries(SAVED_META).map(([k, m]) => `<button class="chip" data-f="${k}">${m[0]}</button>`).join('')}
    </div>
    <div id="sv">${skelRows(4)}</div>`);

  const load = async () => {
    try {
      S.saved = await GET('/saved' + (filter ? '?item_type=' + filter : ''));
      $('#sv').innerHTML = S.saved.length ? S.saved.map(it => {
        const [lbl, ic, c, bg] = SAVED_META[it.item_type] || ['Item', I.book, 'var(--muted)', 'var(--surface-2)'];
        return `<div class="list-item">
          <div class="item-icon" style="background:${bg};color:${c}">${ic}</div>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:14px">${esc(it.title)}</div>
            <div class="tiny muted">${lbl} · ${ago(it.created_at)}</div></div>
          <button class="btn btn-ghost btn-sm" data-open="${it.id}">Open</button>
          <button class="btn btn-danger btn-sm" data-del="${it.id}">${I.trash}</button></div>`;
      }).join('') : `<div class="empty">${I.book}<h3>Nothing saved yet</h3>
        <div class="tiny">Save interviews, canvas designs and reviews to find them here</div></div>`;

      $$('[data-del]').forEach(b => b.onclick = async () => {
        if (!confirm('Delete this item?')) return;
        try { await DEL('/saved/' + b.dataset.del); toast('Deleted', 'ok'); load(); }
        catch (e) { toast(e.message, 'err'); }
      });
      $$('[data-open]').forEach(b => b.onclick = () => openSaved(S.saved.find(x => x.id === b.dataset.open)));
    } catch (e) { $('#sv').innerHTML = `<div class="empty"><h3>${esc(e.message)}</h3></div>`; }
  };
  $$('#savedFilters .chip').forEach(c => c.onclick = () => {
    $$('#savedFilters .chip').forEach(x => x.classList.remove('on'));
    c.classList.add('on'); filter = c.dataset.f || null; load();
  });
  load();
}

function openSaved(it) {
  if (!it) return;
  const p = it.payload || {};
  let body = '';
  if (it.item_type === 'canvas') {
    body = `${p.nodes?.length ? canvasPreviewSvg(p.nodes, p.connections || []) : ''}
      ${p.generated_code ? `<div class="sp-label" style="color:var(--muted)">GENERATED PYTHON</div>
      <pre class="out-block" style="background:var(--editor-bg)">${esc(p.generated_code)}</pre>` : ''}`;
  } else if (it.item_type === 'interview') {
    body = `<div class="sp-label" style="color:var(--muted)">QUESTION</div>
      <p style="font-size:13.5px;line-height:1.6;margin-bottom:14px">${esc(p.question || '')}</p>
      ${(p.transcript || []).map(t => `<div style="margin-bottom:9px;font-size:13px">
        <b>${t.role === 'student' ? 'You' : 'Interviewer'}:</b> ${esc(t.text)}</div>`).join('')}
      ${p.feedback ? `<div class="card card-pad" style="margin-top:14px;background:var(--cyan-soft)">
        <b>${esc(p.feedback.overall_rating || '')}</b><br>${esc(p.feedback.summary || '')}</div>` : ''}`;
  } else {
    body = `${p.code ? `<pre class="out-block" style="background:var(--editor-bg);margin-bottom:12px">${esc(p.code)}</pre>` : ''}
      ${p.review ? `<p style="font-size:13.5px;line-height:1.6">${esc(p.review.summary || '')}</p>` : ''}
      ${(p.messages || []).map(m => `<div style="margin-bottom:8px;font-size:13px"><b>${esc(m.role)}:</b> ${esc(m.text)}</div>`).join('')}
      ${it.item_type === 'tutor_chat' && (p.messages || []).length ? `<button class="btn btn-lg" id="continueChatBtn" style="width:100%;margin-top:14px">Continue this chat</button>` : ''}
      ${it.item_type === 'editor_code' && p.code ? `<button class="btn btn-lg" id="openInEditorBtn" style="width:100%;margin-top:14px">Open in editor</button>` : ''}`;
  }
  modal(`<h3>${esc(it.title)}</h3>
    <div class="tiny muted" style="margin-bottom:16px">${ago(it.created_at)}</div>
    ${body}
    <button class="btn btn-ghost" style="width:100%;margin-top:18px"
      onclick="this.closest('.modal-bg').remove()">Close</button>`, true);
  if ($('#continueChatBtn')) $('#continueChatBtn').onclick = () => {
    S.chat.msgs = (p.messages || []).slice();
    closeModals();
    go('#/chat');
  };
  if ($('#openInEditorBtn')) $('#openInEditorBtn').onclick = () => {
    S.editor.code = p.code;
    if (p.language) S.editor.lang = p.language;
    closeModals();
    go('#/editor');
  };
}

function canvasPreviewSvg(nodes, conns) {
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
  const pad = 90;
  const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad;
  const minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
  const w = maxX - minX, h = maxY - minY;
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  let out = '';
  for (const c of conns) {
    const a = byId[c.fromNodeId], b = byId[c.toNodeId];
    if (!a || !b) continue;
    out += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#8FB3C0" stroke-width="2"/>`;
  }
  for (const n of nodes) {
    const s = SHAPES[n.type] || SHAPES.process;
    out += n.type === 'decision'
      ? `<polygon points="${n.x},${n.y - s.h / 2} ${n.x + s.w / 2},${n.y} ${n.x},${n.y + s.h / 2} ${n.x - s.w / 2},${n.y}" fill="${s.fill}" stroke="${s.stroke}" stroke-width="2"/>`
      : `<rect x="${n.x - s.w / 2}" y="${n.y - s.h / 2}" width="${s.w}" height="${s.h}" rx="${n.type === 'start' || n.type === 'end' ? s.h / 2 : 9}" fill="${s.fill}" stroke="${s.stroke}" stroke-width="2"/>`;
    out += `<text x="${n.x}" y="${n.y + 4}" text-anchor="middle" font-size="11" font-weight="600"
      fill="${s.text}" font-family="Inter">${esc((n.label || '').slice(0, 24))}</text>`;
  }
  return `<div style="border:1px solid var(--line);border-radius:var(--r);overflow:hidden;margin-bottom:14px;background:#fff">
    <svg viewBox="${minX} ${minY} ${w} ${h}" style="width:100%;max-height:340px;display:block">${out}</svg></div>`;
}

/* ═══════════════ PROFILE ═══════════════ */
async function viewProfile() {
  const u = S.user || {};
  const av = avatarUrl(u);
  shell('Profile', 'Your account', `
    <div class="card card-pad" style="text-align:center;margin-bottom:18px">
      <label style="cursor:pointer;display:inline-block;position:relative">
        <div class="avatar" style="width:86px;height:86px;font-size:28px;margin:0 auto">
          ${av ? `<img src="${av}" alt="">` : esc(initials(u.name))}</div>
        <input type="file" id="avIn" accept="image/*" hidden>
        <div style="position:absolute;right:-2px;bottom:-2px;width:28px;height:28px;border-radius:50%;
          background:var(--cyan);color:#fff;display:grid;place-items:center;border:2.5px solid var(--surface)">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M3 8h4l2-3h6l2 3h4v12H3z"/><circle cx="12" cy="13" r="3.5"/></svg></div>
      </label>
      <div style="font-size:20px;font-weight:700;margin-top:14px" id="nameLbl">${esc(u.name || '')}
        <button id="editName" style="color:var(--muted);margin-left:4px">
        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M4 20h4L20 8l-4-4L4 16z"/></svg></button></div>
      <div class="tiny muted">${esc(u.email || '')}</div>
      <div class="row" style="justify-content:center;gap:8px;margin-top:12px">
        <span class="pill pill-cyan">${esc(u.role || 'student')}</span>
        <span class="pill pill-amber">${I.bolt} ${u.xp ?? 0} XP</span>
        <span class="pill pill-gray">${u.streak ?? 0} day streak</span>
      </div>
    </div>
    <div class="card card-pad" style="margin-bottom:18px">
      <div class="section-title">Backend connection</div>
      <div class="row between wrap" style="gap:10px">
        <code class="tiny" style="color:var(--muted)">${esc(CONFIG.API)}</code>
        <button class="btn btn-ghost btn-sm" id="apiBtn">Change</button></div>
    </div>
    <button class="btn btn-danger btn-lg" style="width:100%" id="outBtn">${I.logout} Sign out</button>`);

  $('#outBtn').onclick = () => { logout(); toast('Signed out'); };
  $('#apiBtn').onclick = () => {
    const v = prompt('Backend API base URL', CONFIG.API);
    if (v) { localStorage.setItem('cz_api', v.trim()); location.reload(); }
  };
  $('#editName').onclick = () => {
    const m = modal(`<h3>Edit name</h3>
      <input class="input" id="nn" value="${esc(u.name || '')}" style="margin:14px 0">
      <div class="row" style="gap:8px">
        <button class="btn btn-ghost" style="flex:1" onclick="this.closest('.modal-bg').remove()">Cancel</button>
        <button class="btn" style="flex:1" id="nnOk">Save</button></div>`);
    $('#nnOk', m).onclick = async () => {
      const name = $('#nn', m).value.trim();
      if (name.length < 2) return;
      try {
        const nu = await PATCH('/auth/me', { name });
        S.user = nu; localStorage.setItem('cz_user', JSON.stringify(nu));
        m.remove(); toast('Name updated', 'ok'); viewProfile();
      } catch (e) { toast(e.message, 'err'); }
    };
  };
  $('#avIn').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try {
      await api('/auth/avatar', { method: 'POST', body: fd });
      S.user = await GET('/auth/me');
      localStorage.setItem('cz_user', JSON.stringify(S.user));
      toast('Photo updated', 'ok'); viewProfile();
    } catch (err) { toast(err.message, 'err'); }
  };
}

/* ═══════════════ BOOT ═══════════════ */
router();