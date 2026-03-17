import asyncio
import datetime
import logging
import os
import pandas as pd
from dotenv import load_dotenv

from fetcher.upstox_client import UpstoxFetcher
from fetcher.upstox_websocket import UpstoxWebSocketClient
from fetcher.data_aggregator import MarketDataAggregator
from processor.indicator_engine import CalculationEngine
from database.supabase_client import RemoteDBWatcher
from main import resample_ohlc # Reuse the resampling logic

load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AsyncMain")

# Global state
aggregator = MarketDataAggregator()
fetcher = UpstoxFetcher()
processor = CalculationEngine()
supabase = RemoteDBWatcher()

async def run_5min_sync_cycle():
    """Performs the 5-minute sync processing using aggregated or fetched data."""
    logger.info(f"--- Starting Sync Job at {datetime.datetime.now()} ---")
    
    instrument_key = "NSE_INDEX|Nifty 50"
    current_time = datetime.datetime.now()
    
    try:
        # 1. Fetch Context Data (1-minute candles for indicators)
        logger.info(f"Fetching 1-minute candles for {instrument_key} via REST for context...")
        raw_1min_candles = fetcher.get_intraday_candles(instrument_key=instrument_key, interval="1minute")
        
        # Resample to 5-minute
        candles = resample_ohlc(raw_1min_candles, '5min')
        
        if not candles:
            logger.warning("No historical candles retrieved via REST. Skipping cycle.")
            return

        # 2. Integrate Live WebSocket Data
        live_candle = aggregator.get_latest_candle(instrument_key, '5minute')
        if live_candle:
            latest_rest_ts = candles[-1][0]
            if live_candle['timestamp'] > latest_rest_ts:
                logger.info(f"Merging live WebSocket candle: {live_candle['timestamp']}")
                candles.append([
                    live_candle['timestamp'],
                    live_candle['open'],
                    live_candle['high'],
                    live_candle['low'],
                    live_candle['close'],
                    live_candle.get('volume', 0),
                    live_candle.get('oi', 0)
                ])

        # 3. Process Options Chain & Futures
        def get_next_nifty_expiry(current_date):
            days_ahead = 3 - current_date.weekday()
            if days_ahead < 0: days_ahead += 7
            return (current_date + datetime.timedelta(days_ahead)).strftime("%Y-%m-%d")

        expiry_date = get_next_nifty_expiry(current_time.date())
        option_chain_data = fetcher.get_option_chain(instrument_key, expiry_date)
        
        # Future Instrument Key (Simplified resolution for now)
        future_instrument_key = "NSE_FO|NIFTY_FUT" # In production, use the resolution logic from main.py
        
        # 4. Technical Indicators
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'])
        df.sort_values('timestamp_dt', inplace=True)
        df.drop(columns=['timestamp_dt'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        df['vol_sma_20'] = df['volume'].rolling(window=20).mean()
        df = processor.compute_standard_indicators(df)
        
        # 5. Additional Macro Metrics (Quotes, VIX, Max Pain, etc.)
        # (Using synchronous fetcher calls for now as UpstoxFetcher is synchronous)
        # In a full async refactor, these would be awaited.
        
        latest = df.iloc[-1].to_dict()
        latest_close = float(latest['close'])
        
        # Fetching other metrics (Simplified for main sync loop)
        vix_quote = fetcher.get_market_quote(["NSE_INDEX|India VIX"])
        vix_data = vix_quote.get("NSE_INDEX|India VIX", {})
        index_macro = processor.compute_index_macro_dict(vix_data)
        
        # ... (Include other logic from main.py as needed) ...
        # For brevity, I'm focusing on the payload generation and upsert
        
        # 6. Generate Payload and Sync to Supabase
        synthetic_ohlc = {
            'open': latest.get('open'),
            'high': latest.get('high'),
            'low': latest.get('low'),
            'close': latest.get('close'),
            'volume': latest.get('volume')
        }
        
        net_gex = processor.compute_net_gex(option_chain_data, latest_close)
        
        # Dummy/Placeholder for complex nested dicts not yet fully async-adapted
        # (In production, these would be fully populated)
        indicators = {
            'rsi_14': latest.get('rsi_14'),
            'vwap': latest.get('vwap'),
            'ema_20': latest.get('ema_20'),
            'ema_50': latest.get('ema_50'),
            'index_macro': index_macro,
            'meta': processor.compute_meta_dict(pd.to_datetime(latest['timestamp']), latest_close),
            'source': 'websocket' if live_candle else 'rest'
        }
        
        payload = processor.generate_5min_sync_payload(
            current_timestamp=pd.to_datetime(latest['timestamp']),
            synthetic_ohlc=synthetic_ohlc,
            net_gex=net_gex,
            indicators_dict=indicators
        )
        
        result = supabase.upsert_5min_summary(payload)
        if result:
            logger.info(f"✅ Successfully synced to Supabase at {latest['timestamp']}!")
        else:
            logger.error("❌ Failed to sync to Supabase.")
            
    except Exception as e:
        logger.error(f"Error during async sync cycle: {e}", exc_info=True)

async def scheduler_loop():
    """Runs the sync cycle every 5 minutes on the boundary."""
    while True:
        now = datetime.datetime.now()
        # Run at 0, 5, 10, ... minutes, offset by 5 seconds
        minutes_until_next = 5 - (now.minute % 5)
        next_run = (now + datetime.timedelta(minutes=minutes_until_next)).replace(second=5, microsecond=0)
        
        sleep_seconds = (next_run - now).total_seconds()
        logger.info(f"Next sync cycle scheduled at {next_run} (in {sleep_seconds:.1f}s)")
        
        await asyncio.sleep(sleep_seconds)
        await run_5min_sync_cycle()

async def main():
    """Main entry point."""
    access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not access_token:
        logger.error("UPSTOX_ACCESS_TOKEN missing!")
        return

    # 1. Initialize WebSocket Client
    # Subscribe to Nifty 50 and Bank Nifty
    instrument_keys = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]
    
    ws_client = UpstoxWebSocketClient(access_token, instrument_keys)
    ws_client.add_callback(aggregator.process_feed)
    
    logger.info("🚀 Starting Async Data Engine...")
    
    # 2. Run WebSocket and Scheduler concurrently
    try:
        await asyncio.gather(
            ws_client.start(),
            scheduler_loop()
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        ws_client.stop()

if __name__ == "__main__":
    asyncio.run(main())
