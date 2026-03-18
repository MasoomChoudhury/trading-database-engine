import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import datetime
from processor.indicator_engine import CalculationEngine
from database.supabase_client import RemoteDBWatcher

class TestSupabaseSync(unittest.TestCase):
    def setUp(self):
        self.processor = CalculationEngine()
        self.current_time = datetime.datetime(2026, 3, 18, 10, 0, 0)
        self.synthetic_ohlc = {
            'open': 22000.0,
            'high': 22050.0,
            'low': 21950.0,
            'close': 22025.0,
            'volume': 100000
        }
        self.indicators = {
            'rsi_14': 55.0,
            'vwap': 22010.0,
            'ema_21': 21980.0,
            'ema_50': 21900.0,
            'opening_range_status': 'Inside Range',
            'index_macro': {},
            'market_internals': 'Mixed Flow',
            'meta': {},
            'pcr': {'live_pcr': 0.8},
            'gamma_walls': {'call_wall_strike': 22100, 'put_wall_strike': 21900},
            'max_pain': {'max_pain_strike': 22000}
        }

    def test_payload_structure(self):
        """Verifies that the generated payload matches the dashboard expectations."""
        payload = self.processor.generate_5min_sync_payload(
            current_timestamp=self.current_time,
            synthetic_ohlc=self.synthetic_ohlc,
            net_gex=123.45,
            indicators_dict=self.indicators
        )
        
        # Check for standardized timestamp
        self.assertIn('timestamp', payload)
        self.assertEqual(payload['timestamp'], self.current_time.isoformat())
        
        # Check for nested OHLC (historical_time_series)
        self.assertIn('historical_time_series', payload)
        hts = payload['historical_time_series']
        self.assertEqual(hts['open'], 22000.0)
        self.assertEqual(hts['close'], 22025.0)
        
        # Check for backward compatibility 'ts'
        self.assertIn('ts', payload)
        self.assertEqual(payload['ts'], self.current_time.isoformat())

    @patch('database.supabase_client.create_client')
    def test_upsert_logging(self, mock_create_client):
        """Verifies that the upsert method logs correctly."""
        # Mock Supabase client
        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase
        
        # Initialize watcher with mock credentials
        with patch.dict('os.environ', {'SUPABASE_URL': 'https://mock.supabase.co', 'SUPABASE_KEY': 'mock_key'}):
            watcher = RemoteDBWatcher()
            
            payload = {'timestamp': '2026-03-18T10:00:00', 'data': 'test'}
            
            # Mock the chain: table().upsert().execute()
            mock_table = MagicMock()
            mock_upsert = MagicMock()
            mock_execute = MagicMock()
            
            mock_supabase.table.return_value = mock_table
            mock_table.upsert.return_value = mock_upsert
            mock_upsert.execute.return_value = MagicMock(data=[payload])
            
            result = watcher.upsert_5min_summary(payload)
            
            self.assertIsNotNone(result)
            mock_supabase.table.assert_called_with('market_data')
            mock_table.upsert.assert_called_with(payload)

if __name__ == '__main__':
    unittest.main()
