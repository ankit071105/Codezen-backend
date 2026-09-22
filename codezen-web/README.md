# CodeZen — Web

Plain HTML/CSS/JS. No build step, no framework, no npm. Three files.

## Run it

The app must be served over `http://` (not opened as a `file://` path), otherwise the
browser blocks the API calls.

```bash
cd codezen-web
python3 -m http.server 5500
```

Open **http://localhost:5500**

Make sure the backend is running:

```bash
cd codezen-backend
source venv/bin/activate
docker-compose up -d
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
```

If your backend is not on `localhost:8000`, click **change** on the login screen
(or **Profile → Backend connection → Change**) and paste the right base URL,
e.g. `http://192.168.1.9:8000/api/v1`. It is remembered in localStorage.

## What's in it

| Screen | What it does |
|---|---|
| **Home** | XP, streak, success rate, room list, AI tool grid |
| **Rooms** | Create / join by invite token, open editor or chat |
| **Editor** | Run, step-debug, complexity, AI review, generated test cases |
| **Algorithm Canvas** | Drag shapes, connect ports, generate Python, run, save |
| **AI Tutor** | Chat routed through the orchestrator (`/agent/message`) |
| **Mock Interview** | Topic → live round → rating + strengths/improvements → save |
| **Progress** | 30-day stats + AI coaching note |
| **Saved** | Filterable library; canvas items redraw as an actual flowchart |
| **Profile** | Avatar upload, name edit, backend URL, sign out |

## The debugger

Python stepping runs **entirely in your browser** using Pyodide (real CPython
compiled to WebAssembly) with a `sys.settrace` tracer. No LLM, no server call —
same idea as PyScope. You get the executed line, every local variable at that
line, and stdout captured up to that point.

**Java, C and C++ can Run but cannot be stepped through.** Being straight about
why: the tracer works because CPython itself is available in the browser. There
is no equivalent lightweight browser runtime for the JVM or for compiled C/C++,
so a step-debugger for them would need a server-side `jdb`/`gdb` session — real
infrastructure, not something that can be faked client-side. The UI says this
plainly rather than showing a fake trace.

First Debug click downloads the Python engine (~10 MB, cached afterwards), so it
needs internet once. Everything after that is instant and offline.

## Backend

No backend changes were needed. It already exposes everything this client uses:

```
POST /auth/login · /auth/register · PATCH /auth/me · POST /auth/avatar
GET  /rooms/ · POST /rooms/ · POST /rooms/join · GET /rooms/{id}
POST /canvas/run · /canvas/analyze · /canvas/generate
POST /agent/message · /agent/interview/start|continue|feedback · GET /agent/progress
GET/POST/DELETE /saved
```

CORS is already `allow_origins=["*"]`, and the client authenticates with a Bearer
token rather than cookies, so no credentialed-CORS problem.

## Canvas shortcuts

- **Click** a shape → edit its label
- **Drag** a shape → move it
- **Right-click** a shape → delete
- **Drag a port dot** onto another shape's port → connect
- Diamond ports: bottom = **YES**, right = **NO**

Labels can be plain English. The backend tries `ast.parse()` first, and only
sends the labels that fail to the LLM — those nodes get an **AI** badge so you
can see exactly what was interpreted.
