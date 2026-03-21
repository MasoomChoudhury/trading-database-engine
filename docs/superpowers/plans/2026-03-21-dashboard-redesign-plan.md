# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the rough slate/Tailwind admin dashboard with a professional Minimal Dark interface — zinc palette, violet accent, top navigation with 4 tabs, live chart, alert feed, and quick actions.

**Architecture:** Single-page app via tab show/hide (no reload). All tab content in one HTML document served by FastAPI. Tab switching via vanilla JS. HTMX for partial data fetches. TradingView Lightweight Charts for charting.

**Tech Stack:** FastAPI + Jinja2, Tailwind CSS (CDN), vanilla JS tab switching, HTMX, TradingView Lightweight Charts v4.1.1

---

## Design Tokens (CSS Variables)

Reference for all tasks:

```css
--bg:       #09090b   /* zinc-950, page background */
--surface:   #18181b   /* zinc-900, cards */
--hover:     #27272a   /* zinc-800, borders, hovers */
--border:    #27272a
--text:      #fff      /* primary text */
--muted:     #71717a   /* zinc-500, secondary text */
--dim:       #52525b   /* zinc-600, labels, timestamps */
--accent:    #8b5cf6   /* violet-500, buttons, active tab */
--accent-h:  #7c3aed   /* violet-600, hover */
--success:   #22c55e   /* green-500 */
--warning:   #eab308   /* yellow-500 */
--danger:    #ef4444   /* red-500 */
```

---

## Task 1: New Backend Endpoints

**Files:**
- Modify: `src/routers/admin.py`

Add four new endpoints after the existing `health_check` endpoint. Also add `import jwt` and `import time` imports at the top of the file.

### 1a. Logs endpoint

```python
@router.get("/logs", response_class=HTMLResponse)
async def get_logs(request: Request, user: str = Depends(get_current_user)):
    """Returns last 100 lines of engine logs as plain text."""
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        result = subprocess.run(
            ["docker", "compose", "-p", "db-engine", "logs", "--tail", "100", "engine"],
            capture_output=True, text=True, timeout=10,
        )
        return HTMLResponse(
            f"<pre style='white-space:pre-wrap;word-break:break-all;color:#a1a1aa'>{result.stdout}</pre>"
        )
    except Exception as e:
        return HTMLResponse(f"<pre style='color:#ef4444'>Error: {e}</pre>", status_code=500)
```

### 1b. Alerts endpoint

```python
@router.get("/alerts", response_class=JSONResponse)
async def get_alerts(request: Request):
    """Returns current alert list as JSON. Polled every 60s by the dashboard."""
    import time as time_mod
    alerts = []

    # Check token expiry via JWT
    try:
        db = RemoteDBWatcher()
        token = db.get_config("UPSTOX_ACCESS_TOKEN")
        if token:
            try:
                import jwt
                decoded = jwt.decode(token, options={"verify_signature": False})
                exp = decoded.get("exp", 0)
                remaining = exp - time_mod.time()
                if remaining < 0:
                    alerts.append({"level": "danger", "message": "Upstox token expired", "time": ""})
                elif remaining < 4 * 3600:
                    alerts.append({"level": "warning", "message": f"Token expires in {int(remaining/3600)}h", "time": ""})
                else:
                    alerts.append({"level": "success", "message": "Upstox token valid", "time": ""})
            except Exception:
                alerts.append({"level": "warning", "message": "Upstox token: could not decode", "time": ""})
        else:
            alerts.append({"level": "warning", "message": "Upstox token: not configured", "time": ""})
    except Exception:
        alerts.append({"level": "info", "message": "Token check unavailable", "time": ""})

    # Check DB connectivity
    try:
        db = RemoteDBWatcher()
        latest = db.get_latest()
        if latest:
            alerts.append({"level": "success", "message": f"DB connected — {latest.get('symbol', 'NIFTY50')}", "time": ""})
        else:
            alerts.append({"level": "danger", "message": "DB: no recent data", "time": ""})
    except Exception:
        alerts.append({"level": "danger", "message": "DB connection failed", "time": ""})

    return alerts
```

### 1c. Restart Engine endpoint

```python
@router.post("/restart-engine", response_class=HTMLResponse)
async def restart_engine(request: Request, user: str = Depends(get_current_user)):
    if not user:
        return HTMLResponse("<span style='color:#ef4444'>Unauthorized</span>", status_code=401)
    try:
        result = subprocess.run(
            ["docker", "compose", "-p", "db-engine", "restart", "engine"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return HTMLResponse("<span style='color:#22c55e'>Engine restarted</span>")
        else:
            return HTMLResponse(f"<span style='color:#ef4444'>Failed: {result.stderr}</span>")
    except Exception as e:
        return HTMLResponse(f"<span style='color:#ef4444'>Error: {e}</span>")
```

### 1d. Pull Latest endpoint

```python
@router.post("/pull-latest", response_class=HTMLResponse)
async def pull_latest(request: Request, user: str = Depends(get_current_user)):
    if not user:
        return HTMLResponse("<span style='color:#ef4444'>Unauthorized</span>", status_code=401)
    try:
        pull = subprocess.run(["git", "pull", "origin", "main"],
                             capture_output=True, text=True, timeout=30)
        if pull.returncode != 0:
            return HTMLResponse(f"<span style='color:#ef4444'>Git pull failed: {pull.stderr}</span>")
        build = subprocess.run(
            ["docker", "compose", "-p", "db-engine", "up", "-d", "--build"],
            capture_output=True, text=True, timeout=300,
        )
        if build.returncode == 0:
            return HTMLResponse("<span style='color:#22c55e'>Pulled and deployed</span>")
        else:
            return HTMLResponse(f"<span style='color:#eab308'>Pull ok, build failed</span>")
    except Exception as e:
        return HTMLResponse(f"<span style='color:#ef4444'>Error: {e}</span>")
```

---

## Task 2: Global CSS & Navigation (base.html)

**Files:**
- Modify: `templates/base.html`

Replace the entire file. Key changes:
- Custom CSS variables + base styles (no Tailwind utility classes for layout)
- New top navigation bar with logo, 4 tabs, user info
- Tab content containers (`.tab-content`, `.tab-content.active`)
- Tab switching JavaScript
- `show_nav` block: nav hidden on login page

The CSS block in base.html should contain ALL global design tokens and base styles. Each template only needs to add its own page-specific styles in `{% block styles %}{% endblock %}`.

**Nav HTML structure:**
```html
<nav class="nav-bar">
  <a href="/" class="nav-logo">
    <div class="nav-logo-mark"></div>
    <div class="nav-logo-text">Data Engine <span>v2</span></div>
  </a>
  <div class="nav-tabs" id="nav-tabs">
    <button class="nav-tab active" data-tab="dashboard">Dashboard</button>
    <button class="nav-tab" data-tab="config">Config</button>
    <button class="nav-tab" data-tab="maintenance">Maintenance</button>
    <button class="nav-tab" data-tab="logs">Logs</button>
  </div>
  <div class="nav-user">
    <span class="nav-user-name">{{ request.session.user }}</span>
    <a href="/auth/logout" class="btn-logout">Logout</a>
  </div>
  <button class="nav-hamburger" id="nav-hamburger" aria-label="Menu">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect y="4" width="20" height="2" rx="1" fill="currentColor"/>
      <rect y="9" width="20" height="2" rx="1" fill="currentColor"/>
      <rect y="14" width="20" height="2" rx="1" fill="currentColor"/>
    </svg>
  </button>
</nav>
```

**Responsive behavior:** Below 640px, hide `.nav-tabs` and show `.nav-hamburger`. Clicking hamburger opens a dropdown with all 4 tabs. Add to the tab switching JS or add a separate hamburger handler.

```javascript
// Responsive hamburger
const hamburger = document.getElementById('nav-hamburger');
const tabs = document.getElementById('nav-tabs');
hamburger?.addEventListener('click', () => {
  tabs.classList.toggle('open');
});
```

**Tab switching JS (before `</body>`):**
```javascript
document.querySelectorAll('.nav-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.getElementById('tab-' + tab)?.classList.add('active');
    // Close mobile menu
    document.getElementById('nav-tabs')?.classList.remove('open');
  });
});
```

**Login page suppression:** Add `{% block show_nav %}{{ false }}{% endblock %}` in `login.html`. In `base.html`, wrap the nav in `{% if show_nav is not false %}`.

---

## Task 3: Login Page

**Files:**
- Modify: `templates/login.html`

Replace the entire file. No nav bar. Centered card on dark background.

Key elements:
- Logo mark (violet square) + wordmark centered at top
- Card with "Sign in" heading
- Username input + Password input (type="password")
- Sign In button (violet, full-width)
- Error message (red background, dot indicator) shown when `{{ error }}` is present
- `{% block show_nav %}{{ false }}{% endblock %}` to hide the nav bar

---

## Task 4: Dashboard Tab

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `src/main_web.py`

Replace `dashboard.html` entirely. This is the `#tab-dashboard` section.

**Structure:**
1. Compact status strip (`.status-strip`) — NIFTY price, DB status, last sync time
2. TradingView chart (`.tv-chart`, height 480px)
3. Two-column grid: Alert Feed (left) + Quick Actions (right)

**JavaScript responsibilities:**
- `initChart()` — initialize TradingView Lightweight Charts, load initial data from `/data/chart`, poll `/data/chart-update` every 30s for live candle updates
- `pollStatus()` — fetch `/admin/alerts` (JSON), update status strip, render alert feed
- `doAction(type)` — POST to `/admin/restart-engine` or `/admin/pull-latest`, show inline spinner → result
- Refresh token → redirect to `/auth/login-upstox`
- `setInterval(pollStatus, 60_000)` for alert polling

The alert feed renders using `.alert-row` divs with colored dots from the alert `level` field.

**Note:** `GET /data/chart` and `GET /data/chart-update` endpoints already exist in `data.py` — no backend changes needed for charting.

---

## Task 5: Config Tab

**Files:**
- Create: `templates/config.html`
- Modify: `src/main_web.py`

Full `.env` editor page. One textarea (monospace font, dark bg, 500px min-height), one Save button.

**Textarea styling:** `background: var(--bg)`, `border: 1px solid var(--border)`, `border-radius: 8px`, `color: var(--text)`, `font-family: monospace`, `min-height: 500px`, `padding: 16px`. **Focus ring:** `box-shadow: 0 0 0 2px var(--accent)` (violet outline ring, matching Tailwind `focus:ring-violet-500`).

**Note:** The `GET /admin/config` endpoint already exists in `admin.py` — it reads `.env` from disk and returns the raw text as HTML. No new endpoint needed.

On page load: fetch `/admin/config` (GET) → populate textarea.
On submit: POST to `/admin/config` with `config_content` form field → show inline status.

**Restart hint** (below Save button): italic muted text: "Note: Restart the engine after saving for changes to take effect."

---

## Task 6: Maintenance Tab

**Files:**
- Create: `templates/maintenance.html`
- Modify: `src/main_web.py`

Three `.card` sections, stacked. Sections are visually grouped with a subtle separator line (1px `var(--border)`) between them.

**Section 1 — Upstox Token (OAuth card):**
- Header: "Upstox Token" + status badge (green dot + "Valid" or yellow dot + "Expiring soon" or red dot + "Expired"). Status comes from `/admin/alerts` (check for token-level alerts).
- Subtext: "Your daily access token expires — refresh without terminal access."
- Button: "Refresh Token" → links to `/auth/login-upstox`

**Section 2 — Data Maintenance (chunk analysis + pruning):**
- Header: "Data Maintenance"
- Sub-section A: **Chunk Analysis** — date input (`type="date"`) labeled "Drop chunks older than", "Analyze" button. Clicking Analyze fetches `POST /data/prune-estimate` with `end_date` and renders the chunk table HTML (chunk name, range end, size columns) in the result area.
- Sub-section B: **Execute Pruning** — "Execute drop_chunks()" button (danger style). Clicking shows a two-step confirm: warning text + "Drop Now" + "Cancel". On confirm, POST to `/data/prune-execute` and render result.

**Section 3 — Data Integrity Audit:**
- Header: "Data Integrity Audit"
- Subtext: "Checks for gaps in 5-min candle series (last 24h)"
- "Run Audit" button → fetches `/data/audit` and renders inline
- Result: green badge with gap count, or red warning with gap details

---

## Task 7: Logs Tab

**Files:**
- Create: `templates/logs.html`
- Modify: `src/main_web.py`

Full-height log viewer.

**Header bar:**
- Left: "Engine Logs" title
- Right: "Auto-scroll" toggle checkbox + "Clear" button + "Download" button

**Log container:** Scrollable `<pre>` styled as terminal. Each line shows timestamp (dim color) + level (INFO/WARN/ERROR colored) + message.

**Download button:** Creates a Blob from the log text and triggers a browser download as `engine-logs-{timestamp}.txt`.

**Auto-scroll toggle:** When enabled, `container.scrollTop = container.scrollHeight` after each log load.

On load: immediately fetch `/admin/logs`, parse each line to extract timestamp/level/message, render structured rows. Auto-scroll to bottom if toggle is on.

---

## Task 8: Route Updates in main_web.py

**Files:**
- Modify: `src/main_web.py`

Add four new route handlers:
```python
@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse("config.html", {"request": request, "user": user})

@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse("maintenance.html", {"request": request, "user": user})

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse("logs.html", {"request": request, "user": user})
```

Update the root `"/"` to render `dashboard.html` instead of the current logic.

---

## Task 9: Add PyJWT to requirements.txt

**Files:**
- Modify: `requirements.txt`

Add `PyJWT` to the Utilities section.
