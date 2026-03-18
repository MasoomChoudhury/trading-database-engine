# Implementation Plan - Migrate Live Data to Upstox WebSocket

This plan outlines the steps for transitioning from polling historical/intraday endpoints to a WebSocket-based live data feed for Upstox.

## Phase 1: Research and Prototyping [checkpoint: 5337557]
- [x] **Task: Research Upstox WebSocket Protocol**
    - [x] Review the provided Upstox WebSocket documentation.
    - [x] Identify correct versions (v2/v3) for Market Data Feed and individual modules.
    - [x] Prototype a basic `asyncio`-based WebSocket connection to Upstox.
- [x] **Task: Conductor - User Manual Verification 'Phase 1: Research and Prototyping' (Protocol in workflow.md)**

## Phase 2: Core WebSocket Implementation [checkpoint: a340eb5]
- [x] **Task: Setup Protobuf Decoding**
    - [x] Install `protobuf` compiler and Python library.
    - [x] Generate Python bindings from `src/fetcher/market_data.proto`.
    - [x] Create a utility to decode incoming WebSocket binary messages into `FeedResponse` objects. [f4d6e9a]
- [x] **Task: Implement `UpstoxWebSocketClient`**
    - [x] Create `src/fetcher/upstox_websocket.py`.
    - [x] Implement connection logic, authentication, and heartbeats.
    - [x] Integrate the Protobuf decoder to process incoming messages.
    - [x] Implement robust auto-reconnect with exponential backoff. [be5646c]
- [x] **Task: Implement Real-time Data Aggregation**
    - [x] Develop a mechanism to aggregate tick data into 1-minute and 5-minute OHLCV candles.
    - [x] Handle concurrent updates for multiple instrument keys. [d8de94b]
- [x] **Task: Conductor - User Manual Verification 'Phase 2: Core WebSocket Implementation' (Protocol in workflow.md)**

## Phase 3: Integration and Orchestration [checkpoint: bbdf6e8]
- [x] **Task: Integrate WebSocket with `IndicatorEngine`** [08d0e7a]
    - [x] Modify the 5-minute sync loop in `src/main.py` (or create a new entry point) to consume WebSocket aggregated candles.
    - [x] Ensure `CalculationEngine` correctly processes the real-time data.
- [x] **Task: Verify Supabase Real-time Sync** [08d0e7a]
    - [x] Confirm that the aggregated live data is being correctly upserted to the `market_data` table in Supabase.
- [x] **Task: Update FastAPI Dashboard for Real-time Status** [08d0e7a]
    - [x] Modify `src/main_web.py` to reflect the WebSocket connection status and latest live sync timestamp.
- [x] **Task: Conductor - User Manual Verification 'Phase 3: Integration and Orchestration' (Protocol in workflow.md)** [08d0e7a]

## Phase 4: Final Validation and Deployment
- [x] **Task: Final Testing and VPS Deployment Readiness**
    - [x] Perform long-running stability tests to ensure no connection leaks.
    - [x] Validate that historical data fetching is still working correctly.
    - [x] Update documentation for VPS deployment with the new WebSocket client.
- [x] **Task: Conductor - User Manual Verification 'Phase 4: Final Validation and Deployment' (Protocol in workflow.md)**
