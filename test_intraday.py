import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from fetcher.upstox_client import UpstoxFetcher
from datetime import datetime
import json

os.environ["UPSTOX_ACCESS_TOKEN"] = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI1NUM3QlUiLCJqdGkiOiI2OWFkNjQ2Y2YyM2VhZTMyM2YwMmJjZmEiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzcyOTcxMTE2LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NzMwMDcyMDB9.U7PO_-Iood4rIVQfeU28kpWq1dbFoaT4RbndoGyVbdc"

fetcher = UpstoxFetcher()
chain = fetcher.get_option_chain("NSE_INDEX|Nifty 50", "2026-03-10")

if chain:
    mid = len(chain) // 2
    ckey = chain[mid].get('call_options', {}).get('instrument_key')
    print("Testing candle fetch for:", ckey)
    candles = fetcher.get_intraday_candles(ckey, "5minute")
    print(f"Candles retrieved: {len(candles)}")
    if candles:
        print("Sample:", candles[0])
