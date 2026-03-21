import os
import requests
from dotenv import load_dotenv, set_key

# Load existing environment
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

API_KEY = os.getenv("UPSTOX_API_KEY")
API_SECRET = os.getenv("UPSTOX_API_SECRET")
REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/")

def generate_auth_url():
    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}"
    return url

def swap_code_for_token(code):
    url = "https://api.upstox.com/v2/login/authorization/token"
    data = {
        'code': code,
        'client_id': API_KEY,
        'client_secret': API_SECRET,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    headers = {'accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print(f"❌ Error: {response.text}")
        return None

def update_supabase_token(token):
    """Update the token in Supabase app_config table."""
    try:
        from supabase import create_client, Client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            print("   ⚠️ Supabase not configured, skipping cloud update")
            return False

        supabase: Client = create_client(url, key)
        data = {"key": "UPSTOX_ACCESS_TOKEN", "value": token}
        supabase.table('app_config').upsert(data).execute()
        print("   ✅ Updated Supabase cloud config")
        return True
    except Exception as e:
        print(f"   ⚠️ Failed to update Supabase: {e}")
        return False

if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        print("❌ Error: UPSTOX_API_KEY or UPSTOX_API_SECRET missing in .env")
        print("\nAdd these to your .env file:")
        print("   UPSTOX_API_KEY=your_api_key")
        print("   UPSTOX_API_SECRET=your_api_secret")
        print("   UPSTOX_REDIRECT_URI=https://database.masoomchoudhury.com/auth/upstox-callback")
        exit(1)

    print("=====================================================")
    print("🌅 Upstox Token Generator")
    print("=====================================================")
    print()
    print("⚠️  IMPORTANT: Auth codes expire in ~30 seconds!")
    print("    Be ready to paste the code IMMEDIATELY after redirect.")
    print()

    # 1. Provide Link
    auth_url = generate_auth_url()
    print(f"1. Open this URL in your browser:\n")
    print(f"   {auth_url}\n")
    print("   Copy this URL and open in browser if needed.\n")

    # 2. Get Code - with timing warning
    print("2. Log in with your Upstox credentials")
    print("3. After login, you WILL be redirected to your callback URL")
    print("4. Look at the redirected URL - it will have ?code=XXXXX in it")
    print()
    print("   Example redirect URL:")
    print("   https://database.masoomchoudhury.com/auth/upstox-callback?code=ABC123&state=xyz")
    print()
    print("5. Copy the code value (e.g., ABC123) and paste below")
    print()
    code = input("Enter the 'code' from the URL: ").strip()

    if code:
        print("\n⏳ Exchanging code for token...")
        token = swap_code_for_token(code)
        if token:
            print(f"\n✅ Token Received: {token[:10]}...{token[-5:]}")

            # 3. Update .env
            set_key(env_path, "UPSTOX_ACCESS_TOKEN", token)
            print("📝 Updated .env with new UPSTOX_ACCESS_TOKEN")

            # 4. Update Supabase cloud config
            print("📝 Updating Supabase cloud config...")
            update_supabase_token(token)

            # 5. Verify the token works
            print("\n5. Verifying token...")
            test_response = requests.get(
                "https://api.upstox.com/v3/market-quote/ltp",
                headers={"Authorization": f"Bearer {token}"},
                params={"instrument_key": "NSE_INDEX|Nifty 50"}
            )
            if test_response.status_code == 200:
                print("   ✅ Token verified and working!")
            else:
                print(f"   ⚠️ Token may have issues: {test_response.status_code}")

            print("\n🚀 Token refreshed! Run test_api_connection.py to verify.")
        else:
            print("\n❌ Failed to retrieve token.")
            print("\nPossible reasons:")
            print("   - Auth code expired (must be used within 30 seconds)")
            print("   - Auth code already used (can only be used once)")
            print("   - Redirect URL not registered in Upstox Developer Portal")
            print("\n   Try again with a NEW code from a fresh login.")
    else:
        print("❌ No code entered. Aborting.")
