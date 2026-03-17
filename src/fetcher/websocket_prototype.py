import asyncio
import os
import json
import ssl
import websockets
import requests
from dotenv import load_dotenv

load_dotenv()

# Upstox API Configuration
API_KEY = os.getenv("UPSTOX_API_KEY")
API_SECRET = os.getenv("UPSTOX_API_SECRET")
ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

# V3 Authorize URL
AUTH_URL_ENDPOINT = "https://api.upstox.com/v3/feed/market-data-feed/authorize"

def get_authorized_url():
    """Fetches the authorized WebSocket URL from Upstox."""
    if not ACCESS_TOKEN:
        print("❌ Error: UPSTOX_ACCESS_TOKEN missing in .env")
        return None
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(AUTH_URL_ENDPOINT, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'success':
            return data['data']['authorizedRedirectUri']
        return None
    except Exception as e:
        print(f"❌ Error fetching authorized URL: {e}")
        return None

async def market_data_feed():
    """Connects to the WebSocket feed and prints received binary data."""
    uri = get_authorized_url()
    if not uri:
        return

    print(f"Connecting to: {uri}")
    
    # Subscription payload
    payload = {
        "guid": "prototype-request-123",
        "method": "sub",
        "data": {
            "mode": "full", # Can be ltpc, full, option_greeks
            "instrumentKeys": ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]
        }
    }

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket Connected!")
            
            # Subscriptions must be sent as binary (JSON encoded to bytes)
            await websocket.send(json.dumps(payload).encode('utf-8'))
            print(f"Sent Subscription: {payload}")

            while True:
                message = await websocket.recv()
                # Message is binary (Protobuf encoded)
                print(f"Received message (len: {len(message)}): {message[:20]}...")
                
    except Exception as e:
        print(f"❌ WebSocket Error: {e}")

if __name__ == "__main__":
    asyncio.run(market_data_feed())
