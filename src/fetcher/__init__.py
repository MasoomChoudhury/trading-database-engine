"""Fetcher module - Broker abstraction layer."""

from .base import DataFetcher, Candle, OptionStrike, MarketQuote, OptionGreeks
from .factory import create_fetcher, register_broker, list_registered_brokers

# Auto-register built-in adapters
from . import upstox_adapter  # noqa: F401

__all__ = [
    # Protocol and types
    "DataFetcher",
    "Candle",
    "OptionStrike",
    "MarketQuote",
    "OptionGreeks",
    # Factory functions
    "create_fetcher",
    "register_broker",
    "list_registered_brokers",
]
