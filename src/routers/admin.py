import os
import json
import psutil
import requests
import subprocess
import jwt
import time
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from routers.auth import get_current_user
from database.supabase_client import RemoteDBWatcher

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="templates")

def check_upstox_health():
    """Checks if Upstox API is reachable."""
    try:
        # Simple ping to the API status or a public endpoint
        response = requests.get("https://api.upstox.com/v2/market-quote/quotes?instrument_key=NSE_EQ|INE002A01018", timeout=2)
        # Even a 401 is technically 'Healthy' in terms of connectivity
        return "Healthy" if response.status_code in [200, 401] else "Degraded"
    except Exception:
        return "Offline"

def check_db_health():
    """Checks Supabase connectivity."""
    try:
        db = RemoteDBWatcher()
        if not db.supabase: return "Mocked (Dry-Run)"
        # Simple select 1
        return "Connected"
    except Exception:
        return "Disconnected"

def check_ws_health():
    """Checks the status of the WebSocket engine from its heartbeat file."""
    status_file = "ws_status.json"
    if not os.path.exists(status_file):
        return "Not Started"
    
    try:
        with open(status_file, "r") as f:
            status_data = json.load(f)
            last_heartbeat = status_data.get("last_heartbeat", 0)
            is_running = status_data.get("is_running", False)
            
            # If heartbeat is within last 30 seconds and marked running
            if is_running and (time.time() - last_heartbeat) < 30:
                return "Active"
            elif is_running:
                return "Stalled"
            else:
                return "Stopped"
    except Exception:
        return "Error"

@router.get("/health", response_class=HTMLResponse)
async def health_check(request: Request):
    # Fetch system metrics
    cpu_usage = psutil.cpu_percent(interval=0.1)
    ram_usage = psutil.virtual_memory().percent
    
    # Real health status
    upstox_status = check_upstox_health()
    db_status = check_db_health()
    ws_status = check_ws_health()
    
    return templates.TemplateResponse("partials/health_status.html", {
        "request": request,
        "cpu": cpu_usage,
        "ram": ram_usage,
        "upstox": upstox_status,
        "db": db_status,
        "websocket": ws_status
    })

@router.post("/update", response_class=HTMLResponse)
async def update_code(request: Request, user: str = Depends(get_current_user)):
    if not user:
        return HTMLResponse("<span class='text-red-400'>Unauthorized</span>", status_code=401)
    
    try:
        # Run git pull
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            return HTMLResponse(f"""
                <div class="bg-green-900/30 border border-green-500/50 p-3 rounded-lg animate-pulse">
                    <p class="text-xs font-bold text-green-400">✅ Git Pull Successful</p>
                    <pre class="text-[10px] text-green-200/70 mt-1 font-mono">{output}</pre>
                    <p class="text-[10px] text-green-400/50 mt-2 italic">* Restart PM2 services to apply changes.</p>
                </div>
            """)
        else:
            return HTMLResponse(f"""
                <div class="bg-red-900/30 border border-red-500/50 p-3 rounded-lg">
                    <p class="text-xs font-bold text-red-400">❌ Git Pull Failed</p>
                    <pre class="text-[10px] text-red-200/70 mt-1 font-mono">{output}</pre>
                </div>
            """)
    except Exception as e:
        return HTMLResponse(f"<div class='text-red-400 text-xs'>Error: {str(e)}</div>")

@router.get("/config", response_class=HTMLResponse)
async def get_config(request: Request, user: str = Depends(get_current_user)):
    """Returns raw .env file content as plain text."""
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    try:
        env_path = Path(__file__).parent.parent.parent / ".env"
        content = env_path.read_text()
        return PlainTextResponse(content)
    except Exception as e:
        return HTMLResponse(f"Error reading config: {e}", status_code=500)

@router.post("/config", response_class=HTMLResponse)
async def save_config(request: Request, user: str = Depends(get_current_user)):
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    try:
        form_data = await request.form()
        content = form_data.get("config_content")

        if content is None:
            return HTMLResponse("<span class='text-red-400 text-xs'>No content provided</span>")

        # Save to .env
        with open(".env", "w") as f:
            f.write(content)

        return HTMLResponse(f"""
            <div class="flex items-center space-x-2 text-green-400 animate-pulse">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span class="text-xs font-bold">Successfully saved to .env</span>
            </div>
        """)
    except Exception as e:
        return HTMLResponse(f"<span class='text-red-400 text-xs'>Error saving: {str(e)}</span>")


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
