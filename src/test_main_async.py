import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Mock dependencies before importing run_5min_sync_cycle
with patch('fetcher.upstox_client.UpstoxFetcher'), \
     patch('fetcher.upstox_websocket.UpstoxWebSocketClient'), \
     patch('database.supabase_client.RemoteDBWatcher'), \
     patch('processor.indicator_engine.CalculationEngine'):
    from main_async import run_5min_sync_cycle, aggregator, fetcher, processor, supabase

class TestMainAsync(unittest.IsolatedAsyncioTestCase):

    @patch('main_async.resample_ohlc')
    async def test_run_5min_sync_cycle_merges_websocket_data(self, mock_resample):
        # 1. Setup Mock REST data (1-minute candles resampled to 5-minute)
        # REST data has a candle at 10:00:00
        rest_candles = [
            ['2024-03-17T10:00:00+05:30', 22000.0, 22010.0, 21990.0, 22005.0, 1000, 50000]
        ]
        mock_resample.return_value = rest_candles
        
        # 2. Setup Mock WebSocket data
        # WebSocket has a NEWER candle at 10:05:00
        ws_candle = {
            'timestamp': '2024-03-17T10:05:00',
            'open': 22005.0,
            'high': 22020.0,
            'low': 22000.0,
            'close': 22015.0,
            'volume': 500,
            'oi': 51000
        }
        aggregator.get_latest_candle = MagicMock(return_value=ws_candle)
        
        # 3. Mock fetcher and processor responses
        fetcher.get_intraday_candles.return_value = [] # Input to mock_resample
        fetcher.get_option_chain.return_value = {}
        fetcher.get_market_quote.return_value = {}
        processor.compute_net_gex.return_value = 100.0
        
        # Mock processor to return a DF with indicators
        def mock_compute_indicators(df):
            df['rsi_14'] = 50.0
            df['vwap'] = 22000.0
            df['ema_20'] = 22000.0
            df['ema_50'] = 22000.0
            return df
        processor.compute_standard_indicators.side_effect = mock_compute_indicators
        
        # Mock generate_5min_sync_payload to return its inputs as a dict
        def mock_generate_payload(current_timestamp, synthetic_ohlc, net_gex, indicators_dict):
            return {
                'timestamp': current_timestamp.isoformat(),
                'open': synthetic_ohlc['open'],
                'high': synthetic_ohlc['high'],
                'low': synthetic_ohlc['low'],
                'close': synthetic_ohlc['close'],
                'volume': synthetic_ohlc['volume'],
                'indicators': indicators_dict
            }
        processor.generate_5min_sync_payload.side_effect = mock_generate_payload
        
        # 4. Run the cycle
        await run_5min_sync_cycle()
        
        # 5. Assertions
        # Check that processor.compute_standard_indicators was called with 2 rows (REST + WS)
        args, _ = processor.compute_standard_indicators.call_args
        df_passed = args[0]
        self.assertEqual(len(df_passed), 2)
        self.assertEqual(df_passed.iloc[1]['timestamp'], '2024-03-17T10:05:00')
        self.assertEqual(df_passed.iloc[1]['close'], 22015.0)
        
        # Check that supabase.upsert_5min_summary was called
        self.assertTrue(supabase.upsert_5min_summary.called)
        payload = supabase.upsert_5min_summary.call_args[0][0]
        self.assertEqual(payload['close'], 22015.0)
        self.assertEqual(payload['indicators']['source'], 'websocket')

if __name__ == '__main__':
    unittest.main()
