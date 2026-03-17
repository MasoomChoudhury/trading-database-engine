import asyncio
import json
import os
import ssl
import logging
import websockets
import requests
from typing import List, Callable, Dict, Any, Optional
from .websocket_decoder import UpstoxDecoder

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UpstoxWebSocket")

class UpstoxWebSocketClient:
    def __init__(self, access_token: str, instrument_keys: List[str], mode: str = "full"):
        self.access_token = access_token
        self.instrument_keys = instrument_keys
        self.mode = mode
        self.uri: Optional[str] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self.is_running = False
        self.reconnect_interval = 1 # Initial reconnect interval in seconds
        self.max_reconnect_interval = 60
        
        self.auth_url_endpoint = "https://api.upstox.com/v3/feed/market-data-feed/authorize"

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Adds a callback function to be called when new data is received and decoded."""
        self.callbacks.append(callback)

    def _get_authorized_url(self) -> Optional[str]:
        """Fetches the authorized WebSocket URL from Upstox."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        try:
            response = requests.get(self.auth_url_endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data['status'] == 'success':
                return data['data']['authorizedRedirectUri']
            logger.error(f"Failed to get authorized URL: {data}")
            return None
        except Exception as e:
            logger.error(f"Error fetching authorized URL: {e}")
            return None

    def _write_status(self, is_running: bool):
        """Writes the current status to a heartbeat file."""
        try:
            with open("ws_status.json", "w") as f:
                json.dump({
                    "last_heartbeat": time.time(),
                    "is_running": is_running
                }, f)
        except Exception as e:
            logger.error(f"Error writing status file: {e}")

    async def _connect(self):
        """Establishes the WebSocket connection and sends the subscription request."""
        self._write_status(True)
        self.uri = self._get_authorized_url()
        if not self.uri:
            self._write_status(False)
            raise Exception("Could not obtain authorized WebSocket URI.")

        logger.info(f"Connecting to Upstox WebSocket: {self.uri}")
        
        # Subscription payload
        payload = {
            "guid": "upstox-client-request",
            "method": "sub",
            "data": {
                "mode": self.mode,
                "instrumentKeys": self.instrument_keys
            }
        }

        async with websockets.connect(self.uri) as websocket:
            self.websocket = websocket
            self.is_running = True
            self.reconnect_interval = 1 # Reset interval on success
            logger.info("✅ Upstox WebSocket Connected!")
            self._write_status(True)
            
            # Subscriptions must be sent as binary
            await self.websocket.send(json.dumps(payload).encode('utf-8'))
            logger.info(f"Subscribed to {len(self.instrument_keys)} instruments in '{self.mode}' mode.")

            async for message in self.websocket:
                self._write_status(True) # Heartbeat on each message
                if isinstance(message, bytes):
                    decoded_data = UpstoxDecoder.decode(message)
                    if decoded_data:
                        for cb in self.callbacks:
                            try:
                                cb(decoded_data)
                            except Exception as e:
                                logger.error(f"Error in WebSocket callback: {e}")
                else:
                    logger.debug(f"Received non-binary message: {message}")

    async def start(self):
        """Starts the WebSocket client with auto-reconnect logic."""
        self.is_running = True
        while self.is_running:
            try:
                await self._connect()
            except (websockets.ConnectionClosed, Exception) as e:
                self._write_status(False)
                if not self.is_running:
                    break
                
                logger.warning(f"WebSocket disconnected/error: {e}. Reconnecting in {self.reconnect_interval}s...")
                await asyncio.sleep(self.reconnect_interval)
                
                # Exponential backoff
                self.reconnect_interval = min(self.reconnect_interval * 2, self.max_reconnect_interval)

    def stop(self):
        """Stops the WebSocket client."""
        self.is_running = False
        self._write_status(False)
        if self.websocket:
            asyncio.create_task(self.websocket.close())
            logger.info("Upstox WebSocket Client stopped.")

