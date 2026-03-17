import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from fetcher.websocket_prototype import get_authorized_url

class TestWebsocketPrototype(unittest.TestCase):
    @patch('requests.get')
    def test_get_authorized_url_success(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'data': {
                'authorizedRedirectUri': 'wss://api.upstox.com/v3/feed/market-data-feed/auth/123'
            }
        }
        mock_get.return_value = mock_response
        
        # Set dummy access token
        with patch.dict(os.environ, {"UPSTOX_ACCESS_TOKEN": "dummy_token"}):
            import fetcher.websocket_prototype
            fetcher.websocket_prototype.ACCESS_TOKEN = "dummy_token"
            url = get_authorized_url()
            self.assertEqual(url, 'wss://api.upstox.com/v3/feed/market-data-feed/auth/123')
            mock_get.assert_called_once()

    def test_get_authorized_url_missing_token(self):
        # Patch ACCESS_TOKEN to None
        with patch.dict(os.environ, {"UPSTOX_ACCESS_TOKEN": ""}):
             # Reloading or manually setting the global is needed if it was already imported
            import fetcher.websocket_prototype
            original_token = fetcher.websocket_prototype.ACCESS_TOKEN
            fetcher.websocket_prototype.ACCESS_TOKEN = None
            try:
                url = get_authorized_url()
                self.assertIsNone(url)
            finally:
                fetcher.websocket_prototype.ACCESS_TOKEN = original_token

if __name__ == '__main__':
    unittest.main()
