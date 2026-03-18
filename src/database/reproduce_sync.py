import asyncio
import datetime
import logging
import pandas as pd
from database.supabase_client import RemoteDBWatcher
from processor.indicator_engine import CalculationEngine

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reproduction")

async def reproduce():
    logger.info("Starting Sync Reproduction...")
    
    supabase = RemoteDBWatcher()
    processor = CalculationEngine()
    
    # Mock data
    current_time = datetime.datetime.now()
    latest_ts = current_time.isoformat()
    
    synthetic_ohlc = {
        'open': 22000.0,
        'high': 22050.0,
        'low': 21950.0,
        'close': 22025.0,
        'volume': 100000
    }
    
    # Mock indicators dict with minimum required keys
    indicators = {
        'rsi_14': 55.0,
        'vwap': 22010.0,
        'ema_21': 21980.0,
        'ema_50': 21900.0,
        'opening_range_status': 'Inside Range',
        'index_macro': {'vix': {'level': 15.0, 'change': 0.1}, 'vix_velocity': 'Neutral', 'vix_crush_detected': False},
        'market_internals': 'Mixed Flow',
        'meta': {
            'ticker': 'NIFTY',
            'live_price': 22025.0,
            'is_index': True,
            'timestamp': latest_ts,
            'market_time': current_time.strftime("%H:%M:%S"),
            'session_phase': 'Morning Trend Establishment'
        }
    }
    
    logger.info(f"Generating payload for timestamp: {latest_ts}")
    payload = processor.generate_5min_sync_payload(
        current_timestamp=pd.to_datetime(latest_ts),
        synthetic_ohlc=synthetic_ohlc,
        net_gex=0.0,
        indicators_dict=indicators
    )
    
    logger.info("Attempting to upsert to Supabase...")
    result = supabase.upsert_5min_summary(payload)
    
    if result:
        logger.info("✅ SUCCESS: Data upserted to Supabase!")
        print(f"Result: {result}")
    else:
        logger.error("❌ FAILURE: Failed to upsert to Supabase.")

if __name__ == "__main__":
    asyncio.run(reproduce())
