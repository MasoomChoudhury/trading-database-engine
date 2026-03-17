# Specification - Migrate Live Data to Upstox WebSocket

## Overview
The goal of this track is to replace the current polling-based approach for live market data (which currently incorrectly uses historical/intraday endpoints) with a real-time WebSocket-based feed from Upstox. This will ensure that live market data is ingested accurately, processed by the indicator engine, and stored in Supabase in real-time.

## Current State
- `src/fetcher/upstox_client.py` uses HTTP polling for intraday and historical candles.
- `src/main.py` schedules these fetches every 5 minutes.
- Data is resampled and processed, but the source for "live" data is high-latency and not designed for real-time sync.

## Target State
- A new WebSocket client (`src/fetcher/upstox_websocket.py`) will manage a persistent connection to Upstox Market Data Feed.
- The WebSocket client will handle authentication and subscription to required instrument keys (Nifty 50, Bank Nifty, and select option strikes).
- Received tick data/LTP will be aggregated into 1-minute and 5-minute candles.
- The system will seamlessly transition from the 5-minute polling loop to a real-time event-driven ingestion model, while maintaining compatibility with the `IndicatorEngine` and `SupabaseClient`.

## Requirements
- **WebSocket Connection:** Reliable, auto-reconnecting WebSocket client using Upstox's latest protocol.
- **Protobuf Decoding:** Integrate the provided `proto3` definition (`src/fetcher/market_data.proto`) to decode binary messages from the WebSocket.
- **Data Aggregation:** Logic to convert real-time ticks into OHLCV candles (1m/5m).
- **Concurrent Processing:** Use `asyncio` to manage the WebSocket feed without blocking the web server or indicator engine.
- **Maintain Indicator Engine:** The WebSocket data must be fed into the existing `CalculationEngine` to calculate GEX, CPR, and other indicators.
- **Supabase Sync:** Correctly upsert real-time processed summaries into Supabase.

## Constraints
- **Upstox Versions:** Carefully navigate Upstox's API versioning (e.g., Market Data Feed might be v2/v3).
- **Non-Breaking:** Do not break the existing historical data fetches or the FastAPI dashboard.
- **VPS Deployment:** Ensure the implementation is robust for persistent running on a VPS.
