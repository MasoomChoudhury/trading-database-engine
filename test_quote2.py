import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from fetcher.upstox_client import UpstoxFetcher
import requests
from datetime import datetime
import json

fetcher = UpstoxFetcher()
endpoint = f"{fetcher.api_url}/option/contract"
params = {"instrument_key": "NSE_INDEX|Nifty 50"}
response = requests.get(endpoint, headers=fetcher.headers, params=params)
contracts = response.json().get('data', [])

valid_expiries = set()
for c in contracts:
    try:
        date_str = c.get('expiry')
        if date_str:
            dt = datetime.fromtimestamp(date_str/1000) # milliseconds
            valid_expiries.add(dt.strftime('%Y-%m-%d'))
    except:
        pass

expiries = sorted(list(valid_expiries))
print("Next 5 expiries:", expiries[:5])

if expiries:
    chain = fetcher.get_option_chain("NSE_INDEX|Nifty 50", expiries[0])
    if chain:
        mid_strike = chain[len(chain)//2]
        ckey = mid_strike.get('call_options', {}).get('instrument_key')
        if ckey:
            quote = fetcher.get_market_quote([ckey])
            print("Keys available in option quote:")
            if ckey in quote:
                q = quote[ckey]
                print(list(q.keys()))
                print("Depth keys:", q.get('depth', {}).keys())
                print("Total Buy Qty from depth?: buy:", sum(item.get('quantity', 0) for item in q.get('depth', {}).get('buy', [])))
                total_buy = q.get('total_buy_quantity', 0)
                print("Root total_buy_quantity:", total_buy)
                print("Full quote dump:", json.dumps(q, indent=2))
