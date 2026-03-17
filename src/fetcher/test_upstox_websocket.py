import unittest
import asyncio
import json
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from fetcher.upstox_websocket import UpstoxWebSocketClient

class TestUpstoxWebSocketClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.access_token = "dummy_token"
        self.instrument_keys = ["NSE_INDEX|Nifty 50"]
        self.client = UpstoxWebSocketClient(self.access_token, self.instrument_keys)

    @patch('requests.get')
    def test_get_authorized_url_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'data': {'authorizedRedirectUri': 'wss://mock.uri'}
        }
        mock_get.return_value = mock_response
        
        uri = self.client._get_authorized_url()
        self.assertEqual(uri, 'wss://mock.uri')

    @patch('websockets.connect')
    @patch('requests.get')
    async def test_websocket_lifecycle(self, mock_get, mock_connect):
        # 1. Mock Authorization
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'data': {'authorizedRedirectUri': 'wss://mock.uri'}
        }
        mock_get.return_value = mock_response
        
        # 2. Mock WebSocket
        mock_ws = AsyncMock()
        # Mocking the context manager
        mock_connect.return_value.__aenter__.return_value = mock_ws
        
        # Mock receiving one message and then closing
        mock_ws.__aiter__.return_value = [b'\x01\x02\x03']
        
        # 3. Add Callback
        callback = MagicMock()
        self.client.add_callback(callback)
        
        # 4. Mock Decoder
        with patch('fetcher.websocket_decoder.UpstoxDecoder.decode') as mock_decode:
            mock_decode.return_value = {'test': 'data'}
            
            # 5. Run a short-lived connection
            try:
                await asyncio.wait_for(self.client._connect(), timeout=1.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                pass
            
            # 6. Verify
            callback.assert_called_once_with({'test': 'data'})
            mock_ws.send.assert_called_once()
            sent_payload = json.loads(mock_ws.send.call_args[0][0].decode('utf-8'))
            self.assertEqual(sent_payload['method'], 'sub')
            self.assertIn("NSE_INDEX|Nifty 50", sent_payload['data']['instrumentKeys'])


if __name__ == '__main__':
    unittest.main()
