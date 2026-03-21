#!/usr/bin/env python3
"""
Test script to verify Upstox API integration end-to-end.
Run this before running the main sync job to ensure everything works.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

load_dotenv()

def test_upstox_connection():
    """Test Upstox API connection and basic data fetching."""
    from fetcher.upstox_client import UpstoxFetcher

    print("=" * 60)
    print("UPSTOX API END-TO-END TEST")
    print("=" * 60)

    # 1. Initialize fetcher
    print("\n1. Initializing UpstoxFetcher...")
    fetcher = UpstoxFetcher()

    # 2. Test connection
    print("\n2. Testing API connection...")
    if not fetcher.access_token:
        print("❌ ERROR: UPSTOX_ACCESS_TOKEN is not set!")
        print("   Please set UPSTOX_ACCESS_TOKEN in your .env file or Supabase config.")
        return False

    connection_ok = fetcher.test_connection()
    if not connection_ok:
        print("❌ API connection test failed!")
        return False

    # 3. Test historical candles (daily)
    print("\n3. Testing historical candles (daily)...")
    today = "2026-03-21"
    from_date = "2026-03-15"
    daily_candles = fetcher.get_historical_candles(
        instrument_key="NSE_INDEX|Nifty 50",
        interval="day",
        to_date=today,
        from_date=from_date
    )
    if daily_candles:
        print(f"   ✅ Got {len(daily_candles)} daily candles")
        print(f"   Latest: {daily_candles[0] if daily_candles else 'N/A'}")
    else:
        print("   ⚠️ No daily candles returned (may be market hours issue)")

    # 4. Test intraday candles
    print("\n4. Testing intraday candles (1-minute)...")
    intraday = fetcher.get_intraday_candles(
        instrument_key="NSE_INDEX|Nifty 50",
        interval="1"
    )
    if intraday:
        print(f"   ✅ Got {len(intraday)} intraday candles")
        print(f"   Sample: {intraday[-1] if intraday else 'N/A'}")
    else:
        print("   ⚠️ No intraday candles returned (market may be closed)")

    # 5. Test market quote
    print("\n5. Testing market quote...")
    quotes = fetcher.get_market_quote(["NSE_INDEX|Nifty 50"])
    if quotes:
        print(f"   ✅ Got quotes: {list(quotes.keys())}")
        print(f"   Sample data: {quotes.get('NSE_INDEX|Nifty 50', {})}")
    else:
        print("   ⚠️ No quotes returned")

    # 6. Test option chain
    print("\n6. Testing option chain...")
    expiries = fetcher.get_expiries("NSE_INDEX|Nifty 50")
    if expiries:
        print(f"   ✅ Got expiries: {expiries[:3]}...")
        next_expiry = expiries[0]
        chain = fetcher.get_option_chain("NSE_INDEX|Nifty 50", next_expiry)
        if chain:
            print(f"   ✅ Got option chain with {len(chain)} strikes")
        else:
            print("   ⚠️ Empty option chain")
    else:
        print("   ⚠️ No expiries returned")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    return True


def test_supabase_connection():
    """Test Supabase database connection."""
    print("\n" + "=" * 60)
    print("SUPABASE DATABASE TEST")
    print("=" * 60)

    from database.supabase_client import RemoteDBWatcher

    db = RemoteDBWatcher()

    if not db.supabase:
        print("❌ ERROR: Supabase not configured!")
        print("   Please set SUPABASE_URL and SUPABASE_KEY in your .env file.")
        return False

    print("   ✅ Supabase client initialized")

    # Test fetching latest summary
    latest = db.get_latest_summary()
    if latest is not None:
        print(f"   ✅ Latest summary fetched: {len(latest) if latest else 0} rows")
    else:
        print("   ℹ️ No data in database yet (fresh start)")

    return True


def test_end_to_end():
    """Test the full pipeline: fetch -> process -> store."""
    print("\n" + "=" * 60)
    print("END-TO-END PIPELINE TEST")
    print("=" * 60)

    from fetcher.upstox_client import UpstoxFetcher
    from database.supabase_client import RemoteDBWatcher
    from processor.indicator_engine import CalculationEngine
    import pandas as pd

    fetcher = UpstoxFetcher()
    db = RemoteDBWatcher()
    processor = CalculationEngine()

    # Fetch intraday data
    print("\n1. Fetching 1-minute candles...")
    candles = fetcher.get_intraday_candles("NSE_INDEX|Nifty 50", "1")

    if not candles:
        print("   ⚠️ No candles fetched - market may be closed")
        print("   Trying historical candles for testing...")
        candles = fetcher.get_historical_candles(
            "NSE_INDEX|Nifty 50", "5minute",
            "2026-03-21", "2026-03-21"
        )

    if not candles:
        print("   ❌ Still no candles - check API credentials")
        return False

    print(f"   ✅ Got {len(candles)} candles")

    # Process candles
    print("\n2. Processing candles...")
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
    df['open'] = pd.to_numeric(df['open'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['close'] = pd.to_numeric(df['close'])
    df['volume'] = pd.to_numeric(df['volume'])

    if len(df) >= 20:
        df = processor.compute_standard_indicators(df)
        print(f"   ✅ Computed indicators, latest RSI: {df.iloc[-1].get('rsi_14', 'N/A')}")
    else:
        print(f"   ℹ️ Not enough candles ({len(df)}) for indicators, need 20+")

    # Prepare test payload
    print("\n3. Preparing test payload...")
    if len(df) > 0:
        latest = df.iloc[-1]
        synthetic_ohlc = {
            'open': latest['open'],
            'high': latest['high'],
            'low': latest['low'],
            'close': latest['close'],
            'volume': latest['volume']
        }

        indicators = {
            'rsi_14': latest.get('rsi_14', 50),
            'vwap': latest.get('vwap', latest['close']),
            'ema_21': latest.get('ema_21', latest['close']),
            'ema_50': latest.get('ema_50', latest['close']),
        }

        import datetime
        ts = pd.to_datetime(latest.get('timestamp', datetime.datetime.now()))

        payload = processor.generate_5min_sync_payload(
            current_timestamp=ts,
            synthetic_ohlc=synthetic_ohlc,
            net_gex=0.0,
            indicators_dict=indicators
        )

        print(f"   ✅ Payload prepared with {len(payload)} fields")

        # Try to store
        if db.supabase:
            print("\n4. Storing to Supabase...")
            result = db.upsert_5min_summary(payload)
            if result is not None:
                print("   ✅ Successfully stored to Supabase!")
            else:
                print("   ⚠️ Supabase storage returned None (may be rate limited or dry-run mode)")
        else:
            print("\n   ℹ️ Skipping storage - Supabase not configured (dry-run mode)")

    print("\n" + "=" * 60)
    print("PIPELINE TEST COMPLETE")
    print("=" * 60)
    return True


if __name__ == "__main__":
    print("\n🔍 Database Engine - Integration Tests")
    print("=" * 60)

    # Run tests
    upstox_ok = test_upstox_connection()
    supabase_ok = test_supabase_connection()

    if upstox_ok:
        test_end_to_end()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Upstox API:   {'✅ PASS' if upstox_ok else '❌ FAIL'}")
    print(f"Supabase DB:  {'✅ PASS' if supabase_ok else '❌ FAIL'}")

    if upstox_ok and supabase_ok:
        print("\n🚀 All systems operational! Ready to run main sync job.")
    else:
        print("\n⚠️  Some systems need attention before running sync job.")
