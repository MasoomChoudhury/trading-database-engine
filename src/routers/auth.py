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
    REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "https://database.masoomchoudhury.com/auth/upstox-callback")

    # Swap Code for Token
    token_url = "https://api.upstox.com/v2/login/authorization/token"
    payload = {
        "code": code,
        "client_id": API_KEY,
        "client_secret": API_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    headers = {
        "accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        resp = requests.post(token_url, data=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        token_data = resp.json()
        token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not token:
            return HTMLResponse(f"""
                <div class='bg-red-900/30 border border-red-500/50 p-4 rounded-xl text-red-200 text-sm'>
                    <p class='font-bold mb-1'>❌ No token in response</p>
                    <p class='text-[10px] opacity-70 font-mono'>{token_data}</p>
                </div>
            """)

        # 1. Update Supabase cloud config
        db = RemoteDBWatcher()
        db.set_config("UPSTOX_ACCESS_TOKEN", token)
        if refresh_token:
            db.set_config("UPSTOX_REFRESH_TOKEN", refresh_token)

        # 2. Update .env on disk (so Docker container picks it up on restart)
        from dotenv import set_key
        import pathlib

        # Find .env relative to this file's location (works in both dev and Docker)
        project_root = pathlib.Path(__file__).resolve().parents[2]
        env_path = project_root / ".env"

        set_key(str(env_path), "UPSTOX_ACCESS_TOKEN", token)
        if refresh_token:
            set_key(str(env_path), "UPSTOX_REFRESH_TOKEN", refresh_token)

        # 3. Notify PM2 / Docker to restart engine so it picks up new token
        restart_msg = ""
        try:
            import subprocess
            subprocess.run(
                ["docker", "compose", "-p", "db-engine", "restart", "engine"],
                capture_output=True, timeout=30,
            )
            restart_msg = "Engine restarted with new token."
        except Exception:
            try:
                subprocess.run(
                    ["pm2", "restart", "db-engine"],
                    capture_output=True, timeout=15,
                )
                restart_msg = "Engine restarted with new token."
            except Exception:
                restart_msg = "⚠ Could not auto-restart engine — please restart manually."

        return HTMLResponse(f"""
            <div class='bg-green-900/30 border border-green-500/50 p-4 rounded-xl text-green-200 text-sm'>
                <p class='font-bold mb-1'>✅ Token Sync Complete</p>
                <p class='text-[10px] opacity-70 mb-1'>
                    Token: <span class='font-mono'>{token[:12]}...{token[-5:]}</span>
                </p>
                <p class='text-[10px] opacity-70'>Updated Supabase cloud config and .env</p>
                <p class='text-[10px] opacity-70 mt-1'>{restart_msg}</p>
            </div>
        """)

    except requests.HTTPError as e:
        return HTMLResponse(f"""
            <div class='bg-red-900/30 border border-red-500/50 p-4 rounded-xl text-red-200 text-sm'>
                <p class='font-bold mb-1'>❌ HTTP Error {e.response.status_code}</p>
                <p class='text-[10px] opacity-70 font-mono'>{e.response.text[:200]}</p>
                <p class='text-[10px] opacity-70 mt-1'>Common cause: auth code expired (30s window) or redirect URI mismatch in Upstox Developer Portal.</p>
            </div>
        """)
    except Exception as e:
        return HTMLResponse(f"""
            <div class='text-red-400 font-mono text-xs p-4'>
                Failed to exchange token: {str(e)}
            </div>
        """)
