import unittest
from datetime import datetime
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from fetcher.data_aggregator import MarketDataAggregator

class TestDataAggregator(unittest.TestCase):
    def setUp(self):
        self.aggregator = MarketDataAggregator()

    def test_candle_bucketing(self):
        # 1. First tick at 10:00:15
        ts1 = int(datetime(2024, 3, 17, 10, 0, 15).timestamp() * 1000)
        feed1 = {
            'feeds': {
                'NSE_INDEX|Nifty 50': {
                    'ltpc': {'ltp': 22000.0, 'ltt': ts1}
                }
            }
        }
        self.aggregator.process_feed(feed1)
        
        # 1-minute candle should be at 10:00:00
        candle1m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '1minute')
        self.assertEqual(candle1m['timestamp'], datetime(2024, 3, 17, 10, 0, 0).isoformat())
        self.assertEqual(candle1m['open'], 22000.0)
        
        # 5-minute candle should be at 10:00:00
        candle5m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '5minute')
        self.assertEqual(candle5m['timestamp'], datetime(2024, 3, 17, 10, 0, 0).isoformat())

        # 2. Second tick at 10:00:45 (same 1m and 5m candle)
        ts2 = int(datetime(2024, 3, 17, 10, 0, 45).timestamp() * 1000)
        feed2 = {
            'feeds': {
                'NSE_INDEX|Nifty 50': {
                    'ltpc': {'ltp': 22010.0, 'ltt': ts2}
                }
            }
        }
        self.aggregator.process_feed(feed2)
        
        candle1m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '1minute')
        self.assertEqual(candle1m['high'], 22010.0)
        self.assertEqual(candle1m['close'], 22010.0)

        # 3. Third tick at 10:01:05 (new 1m candle, same 5m candle)
        ts3 = int(datetime(2024, 3, 17, 10, 1, 5).timestamp() * 1000)
        feed3 = {
            'feeds': {
                'NSE_INDEX|Nifty 50': {
                    'ltpc': {'ltp': 22005.0, 'ltt': ts3}
                }
            }
        }
        self.aggregator.process_feed(feed3)
        
        candle1m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '1minute')
        self.assertEqual(candle1m['timestamp'], datetime(2024, 3, 17, 10, 1, 0).isoformat())
        self.assertEqual(candle1m['open'], 22005.0)
        
        candle5m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '5minute')
        self.assertEqual(candle5m['high'], 22010.0)
        self.assertEqual(candle5m['close'], 22005.0)

        # 4. Fourth tick at 10:05:01 (new 1m and new 5m candle)
        ts4 = int(datetime(2024, 3, 17, 10, 5, 1).timestamp() * 1000)
        feed4 = {
            'feeds': {
                'NSE_INDEX|Nifty 50': {
                    'ltpc': {'ltp': 22020.0, 'ltt': ts4}
                }
            }
        }
        self.aggregator.process_feed(feed4)
        
        candle5m = self.aggregator.get_latest_candle('NSE_INDEX|Nifty 50', '5minute')
        self.assertEqual(candle5m['timestamp'], datetime(2024, 3, 17, 10, 5, 0).isoformat())
        self.assertEqual(candle5m['open'], 22020.0)

if __name__ == '__main__':
    unittest.main()
