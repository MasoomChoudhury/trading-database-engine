import os
import requests
from dotenv import load_dotenv, set_key

# Load existing environment
env_path = os.path.join(os.getcwd(), '.env')
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

if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        print("❌ Error: UPSTOX_API_KEY or UPSTOX_API_SECRET missing in .env")
        exit(1)

    print("=====================================================")
    print("🌅 Upstox Daily Token Generator")
    print("=====================================================")
    
    # 1. Provide Link
    auth_url = generate_auth_url()
    print(f"\n1. Open this URL in your browser and Log In:\n\n{auth_url}\n")
    
    # 2. Get Code
    print("2. After logging in, you will be redirected to a (likely dead) page.")
    print("   Copy the 'code' parameter from the URL bar.")
    code = input("\nEnter the 'code' here: ").strip()
    
    if code:
        token = swap_code_for_token(code)
        if token:
            print(f"\n✅ Token Received: {token[:10]}...{token[-5:]}")
            
            # 3. Update .env
            set_key(env_path, "UPSTOX_ACCESS_TOKEN", token)
            print("📝 Updated .env with new UPSTOX_ACCESS_TOKEN")
            
            # 4. Suggest Restart
            print("\n🚀 Now restart your engine:")
            print("   pm2 restart db-engine")
        else:
            print("❌ Failed to retrieve token. Check your Secret/Code.")
    else:
        print("❌ No code entered. Aborting.")
