import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from fetcher.upstox_client import UpstoxFetcher
import requests
import json
from datetime import datetime

fetcher = UpstoxFetcher()

def get_current_nifty_expiry(api_url, headers):
    endpoint = f"{api_url}/option/contract"
    params = {"instrument_key": "NSE_INDEX|Nifty 50"}
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        contracts = response.json().get('data', [])
        if not contracts:
            return None
        valid_expiries = set()
        for c in contracts:
            try:
                date_str = c.get('expiry')
                if date_str:
                    dt = datetime.fromtimestamp(date_str/1000)
                    if dt.date() >= datetime.utcnow().date():
                        valid_expiries.add(dt.strftime('%Y-%m-%d'))
            except (ValueError, TypeError):
                continue
        if valid_expiries:
            sorted_expiries = sorted(list(valid_expiries))
            return sorted_expiries[0]
        return None
    except Exception as e:
        print(e)
        return None

expiry = get_current_nifty_expiry(fetcher.api_url, fetcher.headers)
print("Expiry:", expiry)
if expiry:
    chain = fetcher.get_option_chain("NSE_INDEX|Nifty 50", expiry)
    if chain:
        print(json.dumps(chain[len(chain)//2], indent=2))
