import os
import requests
import datetime
import urllib.parse
from dotenv import load_dotenv
import time

from database.supabase_client import RemoteDBWatcher

load_dotenv()

class UpstoxFetcher:
    # Rate limiting: Upstox typically allows ~100 requests/minute
    _last_request_time = 0
    _min_request_interval = 0.6  # seconds between requests

    def __init__(self):
        self.api_url_v2 = "https://api.upstox.com/v2"
        self.api_url_v3 = "https://api.upstox.com/v3"
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

    def _rate_limit(self):
        """Apply rate limiting between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: dict = None, base_url: str = None) -> dict:
        """
        Makes a rate-limited HTTP GET request to Upstox API.
        Returns the parsed JSON response or empty dict on error.
        """
        self._rate_limit()

        url = endpoint if endpoint.startswith('http') else f"{base_url or self.api_url_v2}{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # Log for debugging
            if data.get('status') != 'success':
                print(f"API Warning: {data.get('message', 'Unknown error')}")

            return data
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text[:500]}")
            return {}
        except Exception as e:
            print(f"Request error: {e}")
            return {}

    def get_historical_candles(self, instrument_key: str, interval: str, to_date: str, from_date: str):
        """
        Fetches historical OHLCV data using Upstox V3 API.

        Args:
            instrument_key: Instrument identifier (e.g., 'NSE_INDEX|Nifty 50')
            interval: Timeframe - '1', '5', '15', '30', '60' for minutes, or use unit parameter
            to_date: End date in 'YYYY-MM-DD' format
            from_date: Start date in 'YYYY-MM-DD' format

        Returns:
            List of candles: [[timestamp, open, high, low, close, volume, oi], ...]
        """
        # Map old-style intervals to new V3 format
        interval_map = {
            '1minute': ('minutes', '1'),
            '5minute': ('minutes', '5'),
            '15minute': ('minutes', '15'),
            '30minute': ('minutes', '30'),
            '60minute': ('hours', '1'),
            '1minute': ('minutes', '1'),
            'day': ('days', '1'),
            '1day': ('days', '1'),
        }

        # Determine unit and interval
        if interval in interval_map:
            unit, num = interval_map[interval]
        elif interval.isdigit():
            # Assume minutes if just a number
            unit, num = 'minutes', interval
        else:
            # Try to parse format like "5minute" or "day"
            import re
            match = re.match(r'(\d+)(.*)', interval)
            if match:
                num, suffix = match.groups()
                suffix = suffix or 'minute'
                if 'hour' in suffix.lower():
                    unit = 'hours'
                elif 'day' in suffix.lower():
                    unit = 'days'
                else:
                    unit = 'minutes'
            else:
                unit, num = 'minutes', '1'

        safe_key = urllib.parse.quote(instrument_key, safe="")
        endpoint = f"{self.api_url_v3}/historical-candle/{safe_key}/{unit}/{num}/{to_date}/{from_date}"

        data = self._make_request(endpoint, base_url="")

        if data.get('status') == 'success' and data.get('data'):
            candles = data['data'].get('candles', [])
            if candles:
                print(f"✅ Fetched {len(candles)} candles for {instrument_key} ({unit}/{num})")
                return candles
            else:
                print(f"⚠️ No candle data returned for {instrument_key}")
        else:
            print(f"❌ Failed to fetch historical candles: {data.get('message', 'Unknown error')}")

        return []

    def get_intraday_candles(self, instrument_key: str, interval: str = "1"):
        """
        Fetches intraday data using Upstox V3 API.

        Args:
            instrument_key: Instrument identifier (e.g., 'NSE_INDEX|Nifty 50')
            interval: Minutes - '1', '5', '15', '30', '60'

        Returns:
            List of candles: [[timestamp, open, high, low, close, volume, oi], ...]
        """
        # Normalize interval to just the number
        interval_num = interval
        if interval.endswith('minute'):
            interval_num = interval.replace('minute', '')
        elif interval.endswith('minutes'):
            interval_num = interval.replace('minutes', '')

        # For intraday, we fetch today's data using minutes unit
        today = datetime.datetime.now().strftime('%Y-%m-%d')

        safe_key = urllib.parse.quote(instrument_key, safe="")
        endpoint = f"{self.api_url_v3}/historical-candle/{safe_key}/minutes/{interval_num}/{today}/{today}"

        data = self._make_request(endpoint, base_url="")

        if data.get('status') == 'success' and data.get('data'):
            candles = data['data'].get('candles', [])
            if candles:
                print(f"✅ Fetched {len(candles)} intraday candles for {instrument_key} ({interval_num}m)")
                return candles
            else:
                print(f"⚠️ No intraday data returned for {instrument_key}. Market may be closed.")
        else:
            print(f"❌ Failed to fetch intraday candles: {data.get('message', 'Unknown error')}")

        return []

    def get_option_chain(self, instrument_key: str, expiry_date: str):
        """
        Get Option Chain for a specific instrument and expiry.
        Useful for calculating Net GEX (Gamma Exposure).

        Uses V2 API: GET /v2/option/chain
        """
        endpoint = f"{self.api_url_v2}/option/chain"
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success' and data.get('data'):
            return data['data']
        return []

    def get_expiries(self, instrument_key: str):
        """
        API to retrieve all the expiries for a given underlying instrument.
        Returns a list of dates like ['2024-10-03', '2024-10-10']

        Uses V2 API: GET /v2/expired-instruments/expiries
        """
        endpoint = f"{self.api_url_v2}/expired-instruments/expiries"
        params = {
            "instrument_key": instrument_key
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success':
            return data['data']
        return []

    def get_future_contracts(self, instrument_key: str, expiry_date: str):
        """
        API to retrieve future contracts for an underlying instrument on a specific expiry date.

        Uses V2 API: GET /v2/expired-instruments/future/contract
        """
        endpoint = f"{self.api_url_v2}/expired-instruments/future/contract"
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry_date
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success':
            return data['data']
        return []

    def get_market_quote(self, instrument_keys: list):
        """
        Fetches the full market quote (LTP, OI, Volume, etc) for multiple instruments at once.

        Uses V2 API: GET /v2/market-quote/quotes

        Args:
            instrument_keys: List of instrument keys like ['NSE_EQ|INE002A01018', 'NSE_FO|12345']

        Returns:
            Dict mapping instrument_key to quote data
        """
        if not instrument_keys:
            return {}

        endpoint = f"{self.api_url_v2}/market-quote/quotes"
        params = {
            "instrument_key": ",".join(instrument_keys)
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success':
            return data['data']
        return {}

    def get_option_greeks(self, instrument_keys: list):
        """
        Fetches the option Greek data (including live IV) for multiple instruments at once.

        Uses V3 API: GET /v3/market-quote/option-greek

        Args:
            instrument_keys: List of option instrument keys like ['NSE_FO|43885', 'NSE_FO|43886']

        Returns:
            Dict mapping instrument_key to Greek data (delta, theta, gamma, vega, iv)
        """
        if not instrument_keys:
            return {}

        endpoint = f"{self.api_url_v3}/market-quote/option-greek"
        params = {
            "instrument_key": ",".join(instrument_keys)
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success':
            return data.get('data', {})
        return {}

    def get_option_contracts(self, instrument_key: str):
        """
        Fetches all option contracts natively for a specific underlying instrument.
        Helpful for mapping multiple active expiries concurrently.

        Uses V2 API: GET /v2/option/contract
        """
        endpoint = f"{self.api_url_v2}/option/contract"
        params = {
            "instrument_key": instrument_key
        }

        data = self._make_request(endpoint, params=params, base_url="")

        if data.get('status') == 'success':
            return data.get('data', [])
        return []

    def test_connection(self) -> bool:
        """
        Tests the API connection and authentication.
        Returns True if successful, False otherwise.
        """
        print("Testing Upstox API connection...")

        # Test with a simple market quote request for a known instrument
        test_instruments = ["NSE_INDEX|Nifty 50"]

        try:
            data = self._make_request(
                f"{self.api_url_v3}/market-quote/ltp",
                params={"instrument_key": test_instruments[0]},
                base_url=""
            )

            if data.get('status') == 'success':
                print("✅ Upstox API connection successful!")
                return True
            else:
                print(f"❌ API test failed: {data.get('message', 'Unknown error')}")
                return False

        except Exception as e:
            print(f"❌ API connection error: {e}")
            return False
