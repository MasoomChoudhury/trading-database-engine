# Adding a New Broker Adapter

This guide explains how to add support for a new broker (e.g., Zerodha, Angel One).

## Overview

The broker abstraction uses a Protocol-based adapter pattern:

```
┌─────────────┐
│   factory   │ ← create_fetcher()
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ DataFetcher │ ← Protocol interface
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Upstox    │     │   Zerodha   │  ← Adapters
└─────────────┘     └─────────────┘
```

## Step-by-Step Guide

### 1. Create the Adapter File

Create `src/fetcher/<broker>_adapter.py`:

```python
"""<Broker Name> data fetcher adapter."""

from typing import List, Dict
from .base import DataFetcher, Candle, OptionStrike, MarketQuote, OptionGreeks
from .factory import register_broker


class <Broker>DataFetcher:
    """<Broker Name> implementation of DataFetcher Protocol."""

    def __init__(self):
        # Initialize your broker's API client
        # self._client = BrokerSDK(...)
        pass

    def get_historical_candles(self, instrument_key, interval, to_date, from_date):
        # Implement using broker's API
        raw = self._client.get_ohlc(...)
        return [self._normalize_candle(c) for c in raw]

    # ... implement all DataFetcher methods ...

    @staticmethod
    def _normalize_candle(raw):
        return Candle(
            timestamp=str(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=int(raw[5]),
            oi=int(raw[6]) if len(raw) > 6 else 0,
        )


# Auto-register with factory
register_broker('<broker_name>', <Broker>DataFetcher)
```

### 2. Register in __init__.py

Add to `src/fetcher/__init__.py`:

```python
from . import <broker>_adapter  # noqa: F401
```

### 3. Configure Environment

Add to your `.env`:

```bash
ACTIVE_BROKER=<broker_name>
```

### 4. Test

```bash
# Test the new broker
python3 -c "from fetcher import create_fetcher; f = create_fetcher(); print(f.test_connection())"
```

## Broker Adapter Checklist

- [ ] Implements all `DataFetcher` Protocol methods
- [ ] Returns standard types (Candle, OptionStrike, etc.)
- [ ] Handles rate limiting appropriately
- [ ] Returns empty lists/dicts on errors (not exceptions)
- [ ] Self-registers with `register_broker()`
- [ ] Added to `__init__.py` imports
- [ ] Tested with `test_connection()`

## Example: Zerodha Adapter Skeleton

```python
class ZerodhaDataFetcher:
    broker_name = "zerodha"

    def __init__(self):
        from kiteconnect import KiteConnect
        api_key = os.getenv("ZERODHA_API_KEY")
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

    def get_historical_candles(self, instrument_key, interval, to_date, from_date):
        # Zerodha uses instrument_token, not instrument_key
        # Map accordingly
        data = self._kite.historical_data(...)
        return [self._normalize_candle(d) for d in data]

    # ... etc ...


register_broker('zerodha', ZerodhaDataFetcher)
```

## Switching Brokers

Simply change the `ACTIVE_BROKER` value:

```bash
# Use Upstox
ACTIVE_BROKER=upstox

# Use Zerodha
ACTIVE_BROKER=zerodha
```

No code changes required!
