import os
import requests
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database.supabase_client import RemoteDBWatcher

router = APIRouter(prefix="/auth", tags=["Authentication"])
templates = Jinja2Templates(directory="templates")

# Mock user for admin panel
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")

def get_current_user(request: Request):
    return request.session.get("user")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login")

@router.get("/login-upstox")
async def login_upstox():
    """Initiates the Upstox OAuth flow by redirecting to their login dialog."""
    api_key = os.getenv("UPSTOX_API_KEY")
    redirect_uri = os.getenv("UPSTOX_REDIRECT_URI")
    # Base URL for Upstox OAuth
    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}"
    return RedirectResponse(url=url)

@router.get("/upstox-callback")
async def upstox_callback(request: Request, code: str = None):
    if not code:
        raise HTTPException(status_code=400, detail="Missing auth code")
    
    # Credentials from .env
    API_KEY = os.getenv("UPSTOX_API_KEY")
    API_SECRET = os.getenv("UPSTOX_API_SECRET")
    REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/")

    # Swap Code for Token
    url = "https://api.upstox.com/v2/login/authorization/token"
    data = {
        'code': code,
        'client_id': API_KEY,
        'client_secret': API_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = requests.post(url, data=data, headers=headers)
        response.raise_for_status()
        token = response.json().get('access_token')
        
        if token:
            # Persistent Storage in Supabase
            db = RemoteDBWatcher()
            db.set_config("UPSTOX_ACCESS_TOKEN", token)
            return HTMLResponse(f"""
                <div class='bg-green-900/30 border border-green-500/50 p-4 rounded-xl text-green-200 text-sm'>
                    <p class='font-bold mb-1'>✅ Token Sync Successful</p>
                    <p class='text-[10px] opacity-70'>Upstox token has been updated in Supabase cloud config.</p>
                </div>
            """)
        else:
            return HTMLResponse("<div class='text-red-400'>Error: No token in response</div>")
            
    except Exception as e:
        return HTMLResponse(f"<div class='text-red-400 font-mono text-xs'>Failed to exchange token: {str(e)}</div>")
