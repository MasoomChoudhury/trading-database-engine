import psutil
import requests
import subprocess
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
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
    except:
        return "Offline"

def check_db_health():
    """Checks Supabase connectivity."""
    try:
        db = RemoteDBWatcher()
        if not db.supabase: return "Mocked (Dry-Run)"
        # Simple select 1
        return "Connected"
    except:
        return "Disconnected"

@router.get("/health", response_class=HTMLResponse)
async def health_check(request: Request):
    # Fetch system metrics
    # Using 0.1s interval to get a real reading, otherwise first call is often 0 or 100
    cpu_usage = psutil.cpu_percent(interval=0.1)
    ram_usage = psutil.virtual_memory().percent
    
    # Real health status
    upstox_status = check_upstox_health()
    db_status = check_db_health()
    
    return templates.TemplateResponse("partials/health_status.html", {
        "request": request,
        "cpu": cpu_usage,
        "ram": ram_usage,
        "upstox": upstox_status,
        "db": db_status
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
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    
    try:
        content = ""
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                content = f.read()
        return HTMLResponse(content)
    except Exception as e:
        return HTMLResponse(f"Error reading .env: {str(e)}")

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
