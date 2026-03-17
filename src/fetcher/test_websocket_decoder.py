import unittest
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from fetcher.market_data_pb2 import FeedResponse, Feed, LTPC
from fetcher.websocket_decoder import UpstoxDecoder

class TestWebsocketDecoder(unittest.TestCase):
    def test_decode_ltpc(self):
        # 1. Create a dummy FeedResponse
        response = FeedResponse()
        response.currentTs = 1710684000000 # Example timestamp
        
        # 2. Add an LTPC feed for Nifty 50
        feed = Feed()
        feed.ltpc.ltp = 22011.55
        feed.ltpc.ltt = 1710684000000
        feed.ltpc.ltq = 50
        feed.ltpc.cp = 21990.10
        
        response.feeds["NSE_INDEX|Nifty 50"].CopyFrom(feed)
        
        # 3. Serialize to binary
        binary_data = response.SerializeToString()
        
        # 4. Decode using our utility
        decoded = UpstoxDecoder.decode(binary_data)
        
        # 5. Assertions
        self.assertIsNotNone(decoded)
        self.assertEqual(int(decoded['currentTs']), 1710684000000)
        self.assertIn("NSE_INDEX|Nifty 50", decoded['feeds'])
        
        nifty_feed = decoded['feeds']["NSE_INDEX|Nifty 50"]
        # Note: MessageToDict converts int64 to string by default for compatibility.
        self.assertEqual(float(nifty_feed['ltpc']['ltp']), 22011.55)
        self.assertEqual(float(nifty_feed['ltpc']['cp']), 21990.10)

if __name__ == '__main__':
    unittest.main()
