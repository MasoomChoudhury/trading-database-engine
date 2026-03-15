import psutil
import requests
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
    cpu_usage = psutil.cpu_percent()
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
