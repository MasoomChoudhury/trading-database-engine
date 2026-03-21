"""Upstox data fetcher adapter implementing DataFetcher Protocol."""

from __future__ import annotations
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

from .base import (
    DataFetcher,
    Candle,
    OptionStrike,
    MarketQuote,
    OptionGreeks,
)
from .factory import register_broker


class UpstoxDataFetcher:
    """
    Upstox implementation of DataFetcher Protocol.

    Wraps the existing UpstoxFetcher client and normalizes responses
    to standard types.
    """

    def __init__(self):
        # Import existing client to maintain backward compatibility
        from fetcher.upstox_client import UpstoxFetcher
        self._client = UpstoxFetcher()

    def get_historical_candles(
        self,
        instrument_key: str,
        interval: str,
        to_date: str,
        from_date: str
    ) -> List[Candle]:
        """Fetch historical OHLCV data."""
        try:
            raw_candles = self._client.get_historical_candles(
                instrument_key, interval, to_date, from_date
            )
        except Exception as e:
            logger.error(f"Error fetching historical candles: {e}")
            return []
        return [self._normalize_candle(c) for c in raw_candles]

    def get_intraday_candles(
        self,
        instrument_key: str,
        interval: str = "1"
    ) -> List[Candle]:
        """Fetch intraday OHLCV data."""
        try:
            raw_candles = self._client.get_intraday_candles(instrument_key, interval)
        except Exception as e:
            logger.error(f"Error fetching intraday candles: {e}")
            return []
        return [self._normalize_candle(c) for c in raw_candles]

    def get_option_chain(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[OptionStrike]:
        """Fetch option chain for a given underlying and expiry."""
        try:
            raw_chain = self._client.get_option_chain(instrument_key, expiry_date)
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return []
        return [self._normalize_option_strike(o) for o in raw_chain]

    def get_expiries(self, instrument_key: str) -> List[str]:
        """Get all available expiry dates for an instrument."""
        try:
            return self._client.get_expiries(instrument_key) or []
        except Exception as e:
            logger.error(f"Error fetching expiries: {e}")
            return []

    def get_future_contracts(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[Dict[str, Any]]:
        """Get future contracts for an instrument and expiry."""
        try:
            return self._client.get_future_contracts(instrument_key, expiry_date) or []
        except Exception as e:
            logger.error(f"Error fetching future contracts: {e}")
            return []

    def get_market_quote(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, MarketQuote]:
        """Fetch market quotes for multiple instruments."""
        try:
            raw_quotes = self._client.get_market_quote(instrument_keys) or {}
        except Exception as e:
            logger.error(f"Error fetching market quote: {e}")
            return {}
        return {
            key: self._normalize_market_quote(key, data)
            for key, data in raw_quotes.items()
        }

    def get_option_greeks(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, OptionGreeks]:
        """Fetch option Greeks for multiple instruments."""
        try:
            raw_greeks = self._client.get_option_greeks(instrument_keys) or {}
        except Exception as e:
            logger.error(f"Error fetching option greeks: {e}")
            return {}
        return {
            key: self._normalize_option_greeks(key, data)
            for key, data in raw_greeks.items()
        }

    def test_connection(self) -> bool:
        """Test API connection and authentication."""
        try:
            return self._client.test_connection()
        except Exception as e:
            logger.error(f"Error testing connection: {e}")
            return False

    @staticmethod
    def _normalize_candle(raw: List) -> Candle:
        """Convert raw Upstox candle to standard Candle type."""
        if len(raw) < 6:
            raise ValueError(f"Candle data must have at least 6 fields, got {len(raw)}")
        return Candle(
            timestamp=str(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=int(raw[5]) if len(raw) > 5 else 0,
            oi=int(raw[6]) if len(raw) > 6 else 0,
        )

    @staticmethod
    def _normalize_option_strike(raw: Dict[str, Any]) -> OptionStrike:
        """Convert raw Upstox option data to standard OptionStrike type."""
        return OptionStrike(
            strike=float(raw.get('strike_price', 0)),
            expiry=str(raw.get('expiry_date', '')),
            option_type=raw.get('option_type', 'CE'),
            instrument_key=raw.get('instrument_key', ''),
            ltp=float(raw.get('ltp', 0)),
            iv=float(raw.get('implied_volatility', 0)),
            volume=int(raw.get('volume', 0)),
            open_interest=int(raw.get('open_interest', 0)),
        )

    @staticmethod
    def _normalize_market_quote(key: str, raw: Dict[str, Any]) -> MarketQuote:
        """Convert raw Upstox quote to standard MarketQuote type."""
        return MarketQuote(
            instrument_key=key,
            ltp=float(raw.get('last_price', 0)),
            open=float(raw.get('ohlc', {}).get('open', 0)),
            high=float(raw.get('ohlc', {}).get('high', 0)),
            low=float(raw.get('ohlc', {}).get('low', 0)),
            close=float(raw.get('ohlc', {}).get('close', 0)),
            volume=int(raw.get('volume', 0)),
            oi=int(raw.get('open_interest', 0)),
        )

    @staticmethod
    def _normalize_option_greeks(key: str, raw: Dict[str, Any]) -> OptionGreeks:
        """Convert raw Upstox Greeks to standard OptionGreeks type."""
        return OptionGreeks(
            instrument_key=key,
            delta=float(raw.get('delta', 0)),
            gamma=float(raw.get('gamma', 0)),
            theta=float(raw.get('theta', 0)),
            vega=float(raw.get('vega', 0)),
            iv=float(raw.get('iv', 0)),
        )


# Register this adapter with the factory
register_broker('upstox', UpstoxDataFetcher)
