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
