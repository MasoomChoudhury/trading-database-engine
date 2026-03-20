"""Standard types and Protocol for broker data fetchers."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, List, Dict, Any, runtime_checkable


@dataclass
class Candle:
    """Standard OHLCV candle representation."""
    timestamp: str      # ISO format: "2024-01-15T09:15:00+05:30"
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0  # Open Interest


@dataclass
class OptionStrike:
    """Standard option contract representation."""
    strike: float
    expiry: str
    option_type: str     # "CE" for Call, "PE" for Put
    instrument_key: str
    ltp: float = 0.0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    volume: int = 0
    open_interest: int = 0


@dataclass
class MarketQuote:
    """Standard market quote representation."""
    instrument_key: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0


@dataclass
class OptionGreeks:
    """Standard option Greeks representation."""
    instrument_key: str
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    iv: float = 0.0


@runtime_checkable
class DataFetcher(Protocol):
    """
    Protocol defining the interface for broker data fetchers.

    All concrete broker adapters must implement these methods.
    The return types are normalized to standard types defined above.
    """

    def get_historical_candles(
        self,
        instrument_key: str,
        interval: str,
        to_date: str,
        from_date: str
    ) -> List[Candle]:
        """Fetch historical OHLCV data."""
        ...

    def get_intraday_candles(
        self,
        instrument_key: str,
        interval: str = "1"
    ) -> List[Candle]:
        """Fetch intraday OHLCV data."""
        ...

    def get_option_chain(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[OptionStrike]:
        """Fetch option chain for a given underlying and expiry."""
        ...

    def get_expiries(self, instrument_key: str) -> List[str]:
        """Get all available expiry dates for an instrument."""
        ...

    def get_future_contracts(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[Dict[str, Any]]:
        """Get future contracts for an instrument and expiry."""
        ...

    def get_market_quote(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, MarketQuote]:
        """Fetch market quotes for multiple instruments."""
        ...

    def get_option_greeks(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, OptionGreeks]:
        """Fetch option Greeks for multiple instruments."""
        ...

    def test_connection(self) -> bool:
        """Test API connection and authentication. Returns True if successful."""
        ...
