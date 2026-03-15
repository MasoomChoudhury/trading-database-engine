import os
import sys
import json
from datetime import datetime
import requests

os.environ["UPSTOX_ACCESS_TOKEN"] = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI1NUM3QlUiLCJqdGkiOiI2OWFkNjQ2Y2YyM2VhZTMyM2YwMmJjZmEiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzcyOTcxMTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NzMwMDcyMDB9.U7PO_-Iood4rIVQfeU28kpWq1dbFoaT4RbndoGyVbdc"
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from fetcher.upstox_client import UpstoxFetcher

fetcher = UpstoxFetcher()
expiries = ['2026-03-10', '2026-03-17']
chain = fetcher.get_option_chain("NSE_INDEX|Nifty 50", expiries[0])

if chain:
    mid = len(chain) // 2
    ckey = chain[mid].get('call_options', {}).get('instrument_key')
    print("Testing quote for key:", ckey)
    quote = fetcher.get_market_quote([ckey])
    print(json.dumps(quote, indent=2))
