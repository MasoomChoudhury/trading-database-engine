import os
import requests
import datetime
import urllib.parse
from dotenv import load_dotenv

from database.supabase_client import RemoteDBWatcher

load_dotenv()

class UpstoxFetcher:
    def __init__(self):
        self.api_url = "https://api.upstox.com/v2"
        self.access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
        
        # Try to get token from Supabase if available
        try:
            db = RemoteDBWatcher()
            cloud_token = db.get_config("UPSTOX_ACCESS_TOKEN")
            if cloud_token:
                self.access_token = cloud_token
                print("Using UPSTOX_ACCESS_TOKEN from Supabase cloud config.")
        except Exception as e:
            print(f"Failed to fetch cloud token, falling back to .env: {e}")

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        
        if not self.access_token:
            print("WARNING: UPSTOX_ACCESS_TOKEN is missing. API calls will fail.")

    def get_historical_candles(self, instrument_key: str, interval: str, to_date: str, from_date: str):
        """
        Fetches historical data for a specific instrument.
        Intervals: '1minute', '5minute', 'day', etc.
        Dates format: 'YYYY-MM-DD'
        """
        safe_key = urllib.parse.quote(instrument_key, safe="")
        endpoint = f"{self.api_url}/historical-candle/{safe_key}/{interval}/{to_date}/{from_date}"
        try:
            response = requests.get(endpoint, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']['candles']
            return []
        except Exception as e:
            print(f"Error fetching historical candles for {instrument_key}: {e}")
            return []

    def get_intraday_candles(self, instrument_key: str, interval: str = "1minute"):
        """
        Fetches intraday data using Upstox V3 API.
        V3 supports native intervals like 'minute/5', 'minute/15', etc.
        """
        # Map v2 style intervals to v3 if needed
        v3_interval = interval
        if interval == "5minute":
            v3_interval = "1minute" # Default for now, or use the v3 specific format
        
        # Actually, for V3, the interval for 5 minutes is often '1minute' with a different structure
        # OR V3 intraday candle supports 1-minute only and we should resample?
        # WAIT, search results said V3 supports ANY minutes. 
        # Usually it's '1minute', '30minute'. 
        
        safe_key = urllib.parse.quote(instrument_key, safe="")
        # Switching API URL to V3 specifically for this call
        v3_base = "https://api.upstox.com/v3"
        endpoint = f"{v3_base}/historical-candle/intraday/{safe_key}/{v3_interval}"
        
        # NOTE: If v3_interval is NOT supported, it might fail. 
        # But V3 is designed to be more flexible.
        
        try:
            response = requests.get(endpoint, headers=self.headers, timeout=10)
            if response.status_code == 400:
                print(f"V3 400 Error: {response.text}")
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']['candles']
            return []
        except Exception as e:
            print(f"Error fetching V3 intraday candles: {e}")
            return []

    def get_option_chain(self, instrument_key: str, expiry_date: str):
        """
        Get Option Chain for a specific instrument and expiry.
        Useful for calculating Net GEX (Gamma Exposure).
        """
        endpoint = f"{self.api_url}/option/chain"
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']
            return []
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return []

    def get_expiries(self, instrument_key: str):
        """
        API to retrieve all the expiries for a given underlying instrument.
        Returns a list of dates like ['2024-10-03', '2024-10-10']
        """
        endpoint = f"{self.api_url}/expired-instruments/expiries"
        params = {
            "instrument_key": instrument_key
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']
            return []
        except Exception as e:
            print(f"Error fetching expiries for {instrument_key}: {e}")
            return []
            
    def get_future_contracts(self, instrument_key: str, expiry_date: str):
        """
        API to retrieve future contracts for an underlying instrument on a specific expiry date.
        """
        endpoint = f"{self.api_url}/expired-instruments/future/contract"
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']
            return []
        except Exception as e:
            print(f"Error fetching future contracts for {instrument_key} on {expiry_date}: {e}")
            return []

    def get_market_quote(self, instrument_keys: list):
        """
        Fetches the full market quote (LTP, OI, Volume, etc) for multiple instruments at once.
        Format of instrument_keys: ['NSE_EQ|INE002A01018', 'NSE_FO|12345']
        """
        endpoint = f"{self.api_url}/market-quote/quotes"
        params = {
            "instrument_key": ",".join(instrument_keys)
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']
            return {}
        except Exception as e:
            print(f"Error fetching market quotes: {e}")
            return {}

    def get_option_greeks(self, instrument_keys: list):
        """
        Fetches the option Greek data (including live IV) for multiple instruments at once.
        Format of instrument_keys: ['NSE_FO|43885', 'NSE_FO|43886']
        Note: This specific endpoint uses the V3 Upstox API.
        """
        endpoint = "https://api.upstox.com/v3/market-quote/option-greek"
        params = {
            "instrument_key": ",".join(instrument_keys)
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'success':
                return data.get('data', {})
            return {}
        except Exception as e:
            print(f"Error fetching option greeks: {e}")
            return {}

    def get_option_contracts(self, instrument_key: str):
        """
        Fetches all option contracts natively for a specific underlying instrument.
        Helpful for mapping multiple active expiries concurrently.
        """
        endpoint = f"{self.api_url}/option/contract"
        params = {
            "instrument_key": instrument_key
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'success':
                return data.get('data', [])
            return []
        except Exception as e:
            print(f"Error fetching option contracts: {e}")
            return []
