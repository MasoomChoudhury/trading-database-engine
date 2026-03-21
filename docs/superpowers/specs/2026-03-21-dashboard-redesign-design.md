# Dashboard Redesign Design Spec

> **Goal:** Transform the existing admin dashboard from a rough slate/Tailwind prototype into a professional Minimal Dark trading engine interface.

---

## 1. Visual Direction

**Theme:** Minimal Dark — near-black zinc palette, ultra-clean surfaces, generous whitespace, subtle borders.

| Token | Value |
|---|---|
| Background | `#09090b` (zinc-950) |
| Surface | `#18181b` (zinc-900) |
| Surface Hover | `#27272a` (zinc-800) |
| Border | `#27272a` |
| Text Primary | `#fff` |
| Text Secondary | `#a1a1aa` (zinc-400) |
| Text Muted | `#52525b` (zinc-600) |
| Accent | `#8b5cf6` (violet-500) |
| Accent Hover | `#7c3aed` (violet-600) |
| Success | `#22c55e` (green-500) |
| Warning | `#eab308` (yellow-500) |
| Danger | `#ef4444` (red-500) |

**Typography:** System sans (no custom font needed — native rendering is clean). Sizes: 10px (micro labels), 12px (body), 14px (headings), 16px (titles), 24px (large stats).

**Borders:** 1px solid `#27272a` everywhere — no heavy shadows, no glows. Subtle is key.

**Radius:** `rounded-lg` (8px) for cards, `rounded-md` (6px) for inputs, `rounded-full` for status dots.

**Spacing:** 4px base unit. Consistent 8px/12px/16px/24px gaps.

---

## 2. Layout

**Navigation:** Top tab bar, fixed, no sidebar. Full viewport width. 4 tabs:

1. **Dashboard** — live monitoring (default/landing tab)
2. **Config** — environment configuration
3. **Maintenance** — pruning, audit, OAuth
4. **Logs** — live engine output

**Nav bar structure:**
- Left: Logo mark (violet square + "Data Engine" wordmark)
- Center: Tab buttons (Dashboard | Config | Maintenance | Logs)
- Right: Username + Logout button

**Tab switching:** JavaScript show/hide of tab content sections (no page reload). Active tab gets violet underline + text color.

**Responsive:** Tabs collapse to hamburger menu below 640px.

---

## 3. Dashboard Tab

### 3a. Compact Status Strip
Thin horizontal bar at the very top of the content area (not the nav bar), just above the chart. Purpose: surface the most critical real-time info at a glance without sacrificing chart height.

```
┌─────────────────────────────────────────────────────────────┐
│  NIFTY50: 23,415.80 ▲ +0.42% │ DB ● Online │ Synced 14:25 │
└─────────────────────────────────────────────────────────────┘
```

- Background: `#18181b`, border-bottom: `#27272a`
- Font: 12px, monospace numbers for price
- Color: white for price, green for positive delta, muted for labels
- Right-aligned: "Last sync: HH:MM" from engine health timestamp

### 3b. TradingView Chart
Full remaining height of the viewport minus the status strip and padding. TradingView Lightweight Charts v4 embedded in a `#tv-chart` div. Background matches `#09090b`. No surrounding card decoration — the chart IS the main content.

### 3c. Alert Feed Panel
Appears below the chart as a scrollable feed. Max height ~200px with overflow-y scroll.

**Structure:** Each alert is a row:
- Left: colored status dot (green=ok, yellow=warning, red=error, blue=info)
- Center: alert message text (10px, muted)
- Right: timestamp (9px, muted)
- Background: `#18181b`, separated by `#27272a` borders

**Alert types:**
- Token expiry warning (yellow) — shown when token expires in <24h
- DB connected N rows (blue) — periodic status check
- Sync gap detected (red)
- Engine restart triggered (blue)
- Schema reload (blue)

**Behavior:** New alerts prepend to top. Max 20 stored. Polled every 60s.

### 3d. Quick Actions Panel
Three buttons in a row below the alert feed:
- **Refresh Token** (violet border, violet text) → triggers OAuth re-auth flow
- **Restart Engine** (muted border, muted text) → `docker compose restart engine`
- **Pull Latest** (muted border, muted text) → `git pull && docker compose up -d --build`

Each shows inline feedback (loading spinner → success/error text) replacing the button label.

---

## 4. Config Tab

Full `.env` file editor. No structural changes from current implementation — just styled to match the new theme.

**Elements:**
- Header: "Environment Configuration" + subtitle
- Subtitle: "Edit .env file directly — changes persist across restarts"
- Textarea: monospace font, `#09090b` background, `#18181b` surface, violet focus ring
- Height: `min-h-[500px]`
- Save button: violet background
- Restart hint: muted italic text below button

---

## 5. Maintenance Tab

Two main sections, stacked:

### 5a. OAuth Re-auth Card
Simple centered card:
- Header: "Upstox Token" with status indicator
- Subtext: "Your access token expires daily. Refresh without terminal access."
- Button: "Refresh Token" → links to `/auth/login-upstox`

### 5b. Data Maintenance Card
Accordion-style or stacked sections:
- **Chunk Analysis** — date range picker → "Analyze" → shows chunk names, sizes, end dates in a table
- **Execute Pruning** — two-step confirm → runs `drop_chunks()` → shows result
- **Data Audit** — runs gap audit → shows gap count (green badge) or red warning with gap details

All styled with `#18181b` cards, `#27272a` borders, violet accents.

---

## 6. Logs Tab

Full-height terminal-style panel. Background: `#09090b`. Font: monospace, 11px, `#a1a1aa`.

**Implementation:** Fetched from backend endpoint `/admin/logs` which streams output from `docker compose -p db-engine logs --tail 100`.

**Structure:**
- Header bar: "Engine Logs" + "Clear" button + "Download" button
- Log container: scrollable, auto-scroll to bottom on load, "Auto-scroll" toggle
- Each log line: timestamp in muted, level (INFO/WARN/ERROR) colored appropriately, message in primary text

**Endpoint needed:** `GET /admin/logs` in `admin.py` that reads last 100 lines from docker compose logs.

---

## 7. Login Page

Minimal, centered card on `#09090b` background. Same styling as dashboard cards:
- Logo + "Data Engine" centered at top
- Username input
- Password input (type="password")
- "Sign In" button (violet)
- Error message in red below form

No navigation bar on the login page.

---

## 8. Component Inventory

| Component | Appearance |
|---|---|
| Status dot | 6px circle, colored (green/yellow/red/blue) |
| Metric card | `#18181b` bg, `#27272a` border, rounded-lg, 8px padding |
| Alert row | `#18181b` bg, `#27272a` bottom border, 6px padding, flex row |
| Action button (primary) | `#8b5cf6` bg, white text, rounded-lg |
| Action button (secondary) | transparent, `#27272a` border, muted text, rounded-lg |
| Tab button | text, `#52525b` default, `#fff` + violet underline when active |
| Input | `#09090b` bg, `#27272a` border, white text, violet focus ring |
| Nav bar | `#111` bg, `#27272a` bottom border, 36px height |

---

## 9. Backend Changes

### New endpoints needed

| Route | Method | Description |
|---|---|---|
| `/admin/logs` | GET | Returns last N lines from docker compose logs |
| `/admin/alerts` | GET | Returns current alert list as JSON |
| `/admin/restart-engine` | POST | Runs `docker compose restart engine` |
| `/admin/pull-latest` | POST | Runs `git pull && docker compose up -d --build` |

### Updated endpoints

| Route | Change |
|---|---|
| `GET /` | Already redirects to dashboard — needs template swap to new design |
| `/admin/health` | Already returns health status — add alert generation |
| `/admin/config` | Already works — restyle the response HTML |
| `/data/prune-estimate` | Already wired — restyle HTML response |
| `/data/prune-execute` | Already wired — restyle HTML response |
| `/data/audit` | Already wired — restyle HTML response |

---

## 10. File Changes

```
templates/base.html          — Restyle nav, tabs, global CSS, fonts
templates/login.html         — Restyle login form
templates/dashboard.html     — Replace entirely: compact strip, chart, alerts, quick actions
templates/config.html       — New: .env editor page
templates/maintenance.html   — New: pruning + audit + OAuth
templates/logs.html          — New: live log viewer
src/routers/admin.py         — Add /logs, /alerts, /restart-engine, /pull-latest endpoints
src/routers/data.py          — Already complete (no changes needed)
src/routers/auth.py          — No changes (already works)
src/database/supabase_client.py — No changes (already complete)
```
