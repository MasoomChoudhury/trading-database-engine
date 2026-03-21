# Broker Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple data fetching from Upstox-specific code using a Protocol-based adapter pattern with factory instantiation.

**Architecture:** Create a `DataFetcher` Protocol in `base.py`, implement it in `upstox_adapter.py` wrapping the existing client, and use a factory function to instantiate based on `ACTIVE_BROKER` environment variable.

**Tech Stack:** Python 3.10+, `typing.Protocol` for structural subtyping, `dataclasses` for type definitions

---

## File Structure

```
src/fetcher/
├── __init__.py           # Updated exports
├── base.py               # NEW: Protocol + type definitions
├── factory.py            # NEW: Broker registry + create_fetcher()
├── upstox_adapter.py     # NEW: DataFetcher implementation
└── upstox_client.py      # UNCHANGED: Existing code (backward compatible)

.env                       # Add ACTIVE_BROKER
.env.example               # Add ACTIVE_BROKER
docs/ADDING_BROKERS.md    # NEW: Documentation
```

---

## Task 1: Create base.py with Protocol and Types

**Files:**
- Create: `src/fetcher/base.py`
- Test: N/A (type definitions only)

- [ ] **Step 1: Create src/fetcher/base.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/masoom/Developer/Database Engine"
git add src/fetcher/base.py
git commit -m "feat: add DataFetcher Protocol and standard types

- Candle, OptionStrike, MarketQuote, OptionGreeks dataclasses
- DataFetcher Protocol for broker abstraction
- All types support runtime_checkable for isinstance checks"
```

---

## Task 2: Create factory.py with Registry

**Files:**
- Create: `src/fetcher/factory.py`
- Modify: `src/fetcher/__init__.py`

- [ ] **Step 1: Create src/fetcher/factory.py**

```python
"""Factory for creating broker data fetcher instances."""

from __future__ import annotations
import os
from typing import Type, Dict

from .base import DataFetcher

# Broker registry: maps broker name to fetcher class
_BROKER_REGISTRY: Dict[str, Type[DataFetcher]] = {}


def register_broker(name: str, fetcher_class: Type[DataFetcher]) -> None:
    """
    Register a broker adapter with the factory.

    Args:
        name: Broker identifier (e.g., 'upstox', 'zerodha')
        fetcher_class: Class implementing DataFetcher Protocol

    Example:
        register_broker('zerodha', ZerodhaDataFetcher)
    """
    if not issubclass(fetcher_class, DataFetcher):
        raise TypeError(
            f"{fetcher_class.__name__} must implement DataFetcher Protocol"
        )
    _BROKER_REGISTRY[name] = fetcher_class


def create_fetcher() -> DataFetcher:
    """
    Create a data fetcher instance based on ACTIVE_BROKER environment variable.

    Returns:
        An instance of the registered DataFetcher implementation

    Raises:
        ValueError: If ACTIVE_BROKER is not registered

    Example:
        fetcher = create_fetcher()  # Uses ACTIVE_BROKER from env
    """
    broker = os.getenv("ACTIVE_BROKER", "upstox").lower()

    if broker not in _BROKER_REGISTRY:
        available = ", ".join(sorted(_BROKER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown broker: '{broker}'. "
            f"Available brokers: {available or '(none registered)'}."
        )

    return _BROKER_REGISTRY[broker]()


def list_registered_brokers() -> list[str]:
    """Return list of all registered broker names."""
    return list(_BROKER_REGISTRY.keys())
```

- [ ] **Step 2: Update src/fetcher/__init__.py**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add src/fetcher/factory.py src/fetcher/__init__.py
git commit -m "feat: add broker factory with registry pattern

- _BROKER_REGISTRY for broker adapter registration
- create_fetcher() reads ACTIVE_BROKER env var
- register_broker() for runtime adapter registration
- Auto-imports upstox_adapter for self-registration"
```

---

## Task 3: Create upstox_adapter.py

**Files:**
- Create: `src/fetcher/upstox_adapter.py`
- Reference: `src/fetcher/upstox_client.py` (existing, unchanged)

- [ ] **Step 1: Create src/fetcher/upstox_adapter.py**

```python
"""Upstox data fetcher adapter implementing DataFetcher Protocol."""

from __future__ import annotations
from typing import List, Dict, Any

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
        raw_candles = self._client.get_historical_candles(
            instrument_key, interval, to_date, from_date
        )
        return [self._normalize_candle(c) for c in raw_candles]

    def get_intraday_candles(
        self,
        instrument_key: str,
        interval: str = "1"
    ) -> List[Candle]:
        """Fetch intraday OHLCV data."""
        raw_candles = self._client.get_intraday_candles(instrument_key, interval)
        return [self._normalize_candle(c) for c in raw_candles]

    def get_option_chain(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[OptionStrike]:
        """Fetch option chain for a given underlying and expiry."""
        raw_chain = self._client.get_option_chain(instrument_key, expiry_date)
        return [self._normalize_option_strike(o) for o in raw_chain]

    def get_expiries(self, instrument_key: str) -> List[str]:
        """Get all available expiry dates for an instrument."""
        return self._client.get_expiries(instrument_key) or []

    def get_future_contracts(
        self,
        instrument_key: str,
        expiry_date: str
    ) -> List[Dict[str, Any]]:
        """Get future contracts for an instrument and expiry."""
        return self._client.get_future_contracts(instrument_key, expiry_date) or []

    def get_market_quote(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, MarketQuote]:
        """Fetch market quotes for multiple instruments."""
        raw_quotes = self._client.get_market_quote(instrument_keys) or {}
        return {
            key: self._normalize_market_quote(key, data)
            for key, data in raw_quotes.items()
        }

    def get_option_greeks(
        self,
        instrument_keys: List[str]
    ) -> Dict[str, OptionGreeks]:
        """Fetch option Greeks for multiple instruments."""
        raw_greeks = self._client.get_option_greeks(instrument_keys) or {}
        return {
            key: self._normalize_option_greeks(key, data)
            for key, data in raw_greeks.items()
        }

    def test_connection(self) -> bool:
        """Test API connection and authentication."""
        return self._client.test_connection()

    @staticmethod
    def _normalize_candle(raw: List) -> Candle:
        """Convert raw Upstox candle to standard Candle type."""
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
```

- [ ] **Step 2: Commit**

```bash
git add src/fetcher/upstox_adapter.py
git commit -m "feat: implement UpstoxDataFetcher adapter

- Wraps existing UpstoxFetcher client
- Normalizes all responses to standard types
- Self-registers with factory on import"
```

---

## Task 4: Update main.py to Use Factory

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Update src/main.py import**

Change line 4 from:
```python
from fetcher.upstox_client import UpstoxFetcher
```

To:
```python
from fetcher import create_fetcher
```

And change line 53 from:
```python
fetcher = UpstoxFetcher()
```

To:
```python
fetcher = create_fetcher()
```

The rest of main.py should work unchanged since the adapter implements the same interface.

- [ ] **Step 2: Verify the import change**

```bash
grep -n "from fetcher" src/main.py
# Should show: from fetcher import create_fetcher
```

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "refactor: use create_fetcher() factory instead of direct UpstoxFetcher

- Switches from hardcoded UpstoxFetcher to factory pattern
- ACTIVE_BROKER env var now controls broker selection"
```

---

## Task 5: Update main_web.py

**Files:**
- Modify: `src/main_web.py`

- [ ] **Step 1: Check main_web.py for Upstox usage**

```bash
grep -n "upstox\|Upstox\|fetcher" src/main_web.py
```

If it imports UpstoxFetcher directly, update to use `create_fetcher()`.

- [ ] **Step 2: Commit (if changes needed)**

```bash
git add src/main_web.py
git commit -m "refactor: use factory pattern in main_web.py"
```

---

## Task 6: Update Environment Configuration

**Files:**
- Modify: `.env`
- Modify: `.env.example`

- [ ] **Step 1: Add ACTIVE_BROKER to .env.example**

Add after the Upstox section:
```bash
# Broker Configuration
ACTIVE_BROKER=upstox  # Options: upstox, zerodha, angel_one
```

- [ ] **Step 2: Add ACTIVE_BROKER to .env**

```bash
echo "ACTIVE_BROKER=upstox" >> .env
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .env
git commit -m "config: add ACTIVE_BROKER environment variable

- Controls which broker adapter factory uses
- Defaults to 'upstox'"
```

---

## Task 7: Create Documentation

**Files:**
- Create: `docs/ADDING_BROKERS.md`

- [ ] **Step 1: Create docs/ADDING_BROKERS.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/ADDING_BROKERS.md
git commit -m "docs: add guide for adding new broker adapters"
```

---

## Task 8: Verification

**Files:**
- Test: `test_api_connection.py`

- [ ] **Step 1: Test the factory pattern**

```bash
cd "/Users/masoom/Developer/Database Engine"
python3 -c "
from fetcher import create_fetcher, list_registered_brokers
print('Registered brokers:', list_registered_brokers())
f = create_fetcher()
print('Created fetcher:', type(f).__name__)
print('Connection test:', f.test_connection())
"
```

Expected output:
```
Registered brokers: ['upstox']
Created fetcher: UpstoxDataFetcher
Connection test: True
```

- [ ] **Step 2: Test broker switching (invalid broker)**

```bash
ACTIVE_BROKER=zerodha python3 -c "from fetcher import create_fetcher; create_fetcher()"
```

Expected: ValueError with available brokers list

- [ ] **Step 3: Run existing tests**

```bash
python3 test_api_connection.py
```

- [ ] **Step 4: Run main.py sync job**

```bash
python3 src/main.py
```

Verify data is still being fetched and stored correctly.

---

## Summary

| Task | Files | Status |
|------|-------|--------|
| 1. base.py | Create | Protocol + types |
| 2. factory.py | Create | Registry + create_fetcher |
| 3. upstox_adapter.py | Create | Upstox implementation |
| 4. main.py | Modify | Use factory |
| 5. main_web.py | Modify | Use factory |
| 6. .env | Modify | Add ACTIVE_BROKER |
| 7. Documentation | Create | ADDING_BROKERS.md |
| 8. Verification | Test | Run tests |
