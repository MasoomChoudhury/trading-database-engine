import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_url = "https://api.upstox.com/v2"
access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json"
}

keys = [
    "NSE_EQ|HDFCBANK",
    "NSE_EQ|RELIANCE",
    "NSE_EQ|ICICIBANK", 
    "NSE_EQ|INFY",
    "NSE_EQ|TCS",
    "NSE_EQ|INE040A01034", # HDFC
    "NSE_EQ|INE002A01018", # RELIANCE
    "NSE_EQ|INE090A01021", # ICICI
    "NSE_EQ|INE009A01021", # INFY
    "NSE_EQ|INE467B01029", # TCS
]

endpoint = f"{api_url}/market-quote/quotes"
params = {
    "instrument_key": ",".join(keys)
}
response = requests.get(endpoint, headers=headers, params=params)
data = response.json()

if data.get('status') == 'success':
    quotes = data['data']
    for k in keys:
        if k in quotes:
            print(f"FOUND: {k} -> {quotes[k].get('last_price')} (VWAP: {quotes[k].get('average_price', 'N/A')})")
        else:
            print(f"NOT FOUND: {k}")
else:
    print(data)
