import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger("DataAggregator")

class MarketDataAggregator:
    def __init__(self):
        # candles[instrument_key][interval] = {ohlcv_dict}
        # interval: '1minute', '5minute'
        self.candles: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _get_candle_timestamp(self, ts_ms: int, interval_minutes: int) -> datetime:
        """Returns the start timestamp of the candle bucket."""
        dt = datetime.fromtimestamp(ts_ms / 1000.0)
        # Round down to the nearest interval boundary
        minute = (dt.minute // interval_minutes) * interval_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)

    def process_feed(self, feed_response: Dict[str, Any]):
        """Processes a decoded FeedResponse dictionary."""
        feeds = feed_response.get('feeds', {})
        for instrument_key, feed in feeds.items():
            # Handle different feed types
            # Priority: fullFeed -> firstLevelWithGreeks -> ltpc
            data = None
            if 'fullFeed' in feed:
                ff = feed['fullFeed']
                if 'marketFF' in ff:
                    data = ff['marketFF'].get('ltpc')
                elif 'indexFF' in ff:
                    data = ff['indexFF'].get('ltpc')
            elif 'full_feed' in feed: # Handle snake_case if any
                ff = feed['full_feed']
                if 'market_ff' in ff:
                    data = ff['market_ff'].get('ltpc')
                elif 'index_ff' in ff:
                    data = ff['index_ff'].get('ltpc')
            elif 'firstLevelWithGreeks' in feed:
                data = feed['firstLevelWithGreeks'].get('ltpc')
            elif 'ltpc' in feed:
                data = feed['ltpc']

            if data:
                self._update_ohlcv(instrument_key, data)

    def _update_ohlcv(self, instrument_key: str, ltpc: Dict[str, Any]):
        """Updates the 1-minute and 5-minute candles with new LTP data."""
        ltp = float(ltpc.get('ltp', 0.0))
        ltt = int(ltpc.get('ltt', 0))
        if ltp == 0 or ltt == 0:
            return

        if instrument_key not in self.candles:
            self.candles[instrument_key] = {
                '1minute': {},
                '5minute': {}
            }

        for interval_name, interval_mins in [('1minute', 1), ('5minute', 5)]:
            ts = self._get_candle_timestamp(ltt, interval_mins)
            ts_str = ts.isoformat()
            
            candle = self.candles[instrument_key][interval_name]
            
            # If the timestamp has changed, the previous candle is "closed"
            if candle and candle.get('timestamp') != ts_str:
                # In a real system, we might emit an event here
                logger.debug(f"Closed {interval_name} candle for {instrument_key}: {candle}")
                # Reset for new candle
                candle.clear()

            if not candle:
                candle.update({
                    'timestamp': ts_str,
                    'open': ltp,
                    'high': ltp,
                    'low': ltp,
                    'close': ltp,
                    'volume': 0 # Volume might need careful handling from vtt if available
                })
            else:
                candle['high'] = max(candle['high'], ltp)
                candle['low'] = min(candle['low'], ltp)
                candle['close'] = ltp
            
            # Note: vtt (Volume Traded Today) can be used to calculate candle volume
            # but it requires tracking the last seen vtt.

    def get_latest_candle(self, instrument_key: str, interval: str = '5minute') -> Optional[Dict[str, Any]]:
        """Returns the current open candle for an instrument."""
        return self.candles.get(instrument_key, {}).get(interval)

    def get_all_latest_candles(self, interval: str = '5minute') -> Dict[str, Dict[str, Any]]:
        """Returns the current open candles for all instruments."""
        result = {}
        for key, intervals in self.candles.items():
            candle = intervals.get(interval)
            if candle:
                result[key] = candle
        return result
