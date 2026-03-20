# Broker Abstraction Refactoring Design

**Date**: 2026-03-21
**Status**: Approved
**Project**: Database Engine

---

## Context

The current `UpstoxFetcher` class in `src/fetcher/upstox_client.py` is tightly coupled to the Upstox API. Switching brokers (e.g., Zerodha, Angel One) requires rewriting the entire data fetching layer. This design introduces a **Protocol-based abstraction** with a factory pattern to enable broker switching via environment configuration.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                            │
│                    uses create_fetcher()                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      factory.py                            │
│   create_fetcher() → reads ACTIVE_BROKER env var          │
│   Returns: UpstoxDataFetcher (or other registered brokers)│
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌───────────┐  ┌───────────┐  ┌───────────┐
    │   base.py │  │ upstox_   │  │ zerodha_  │
    │ (Protocol)│◄─┤ adapter   │  │ adapter   │
    └───────────┘  └───────────┘  └───────────┘
```

---

## New Files

### 1. `src/fetcher/base.py`

Defines the `DataFetcher` Protocol and standard types.

**Protocol Methods:**
- `get_historical_candles(instrument_key, interval, to_date, from_date) -> List[Candle]`
- `get_intraday_candles(instrument_key, interval) -> List[Candle]`
- `get_option_chain(instrument_key, expiry_date) -> List[OptionStrike]`
- `get_expiries(instrument_key) -> List[str]`
- `get_future_contracts(instrument_key, expiry_date) -> dict`
- `get_market_quote(instrument_keys) -> dict`
- `get_option_greeks(instrument_keys) -> dict`
- `test_connection() -> bool`

**Standard Types:**
```python
@dataclass
class Candle:
    timestamp: str      # ISO format
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0

@dataclass
class OptionStrike:
    strike: float
    expiry: str
    option_type: str     # "CE" or "PE"
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
    instrument_key: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
```

### 2. `src/fetcher/factory.py`

Factory for creating fetcher instances.

```python
_BROKER_REGISTRY: Dict[str, Type[DataFetcher]] = {}

def register_broker(name: str, fetcher_class: Type[DataFetcher]) -> None:
    """Register a broker adapter."""
    _BROKER_REGISTRY[name] = fetcher_class

def create_fetcher() -> DataFetcher:
    """Create a fetcher based on ACTIVE_BROKER env var."""
    broker = os.getenv("ACTIVE_BROKER", "upstox")
    if broker not in _BROKER_REGISTRY:
        available = ", ".join(_BROKER_REGISTRY.keys())
        raise ValueError(f"Unknown broker: {broker}. Available: {available}")
    return _BROKER_REGISTRY[broker]()
```

### 3. `src/fetcher/upstox_adapter.py`

Wraps existing `UpstoxFetcher` with type normalization.

- Imports and wraps `UpstoxFetcher` from `upstox_client.py`
- Converts raw API responses to standard types
- Implements `DataFetcher` Protocol
- **Does NOT modify** `upstox_client.py` (backward compatible)

### 4. `docs/ADDING_BROKERS.md`

Documentation for adding new broker adapters.

---

## Files to Modify

### `src/fetcher/__init__.py`

Export factory and types:
```python
from .base import DataFetcher, Candle, OptionStrike, MarketQuote, OptionGreeks
from .factory import create_fetcher, register_broker

__all__ = [
    "DataFetcher",
    "Candle",
    "OptionStrike",
    "MarketQuote",
    "OptionGreeks",
    "create_fetcher",
    "register_broker",
]
```

### `src/main.py`

Before:
```python
from fetcher.upstox_client import UpstoxFetcher
fetcher = UpstoxFetcher()
```

After:
```python
from fetcher.factory import create_fetcher
fetcher = create_fetcher()  # Reads ACTIVE_BROKER from env
```

### `src/main_web.py`

Same pattern - use `create_fetcher()` for consistency.

### `.env`

Add:
```bash
ACTIVE_BROKER=upstox  # Switch with: upstox, zerodha, etc.
```

### `.env.example`

Add:
```bash
# Broker Configuration
ACTIVE_BROKER=upstox  # Options: upstox, zerodha, angel_one
```

---

## Migration Plan

1. Create `src/fetcher/base.py` with Protocol and types
2. Create `src/fetcher/factory.py` with registry
3. Create `src/fetcher/upstox_adapter.py` wrapping existing client
4. Update `src/fetcher/__init__.py` exports
5. Update `src/main.py` to use factory
6. Update `src/main_web.py` to use factory
7. Update `.env` and `.env.example`
8. Create `docs/ADDING_BROKERS.md`
9. Run tests to verify

---

## What Stays the Same

| Component | Reason |
|-----------|--------|
| `src/fetcher/upstox_client.py` | Backward compatible, wrapped by adapter |
| `processor/indicator_engine.py` | Pure math, broker-agnostic |
| `database/supabase_client.py` | Already abstracted |
| `main.py` calculation logic | Works on standardized types |

---

## Adding a New Broker

See `docs/ADDING_BROKERS.md` for full instructions.

Quick summary:
1. Create `src/fetcher/<broker>_adapter.py`
2. Implement `DataFetcher` Protocol
3. Register with `register_broker('name', BrokerDataFetcher)`
4. Set `ACTIVE_BROKER=name` in `.env`

---

## Verification

1. **Run tests**: `python3 test_api_connection.py`
2. **Test broker switching**: Change `ACTIVE_BROKER` env var
3. **Run sync job**: `python3 src/main.py`
4. **Verify data integrity**: Check Supabase for correct data
