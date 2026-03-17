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

## Phase 3: Integration and Orchestration
- [ ] **Task: Integrate WebSocket with `IndicatorEngine`**
    - [ ] Modify the 5-minute sync loop in `src/main.py` (or create a new entry point) to consume WebSocket aggregated candles.
    - [ ] Ensure `CalculationEngine` correctly processes the real-time data.
- [ ] **Task: Verify Supabase Real-time Sync**
    - [ ] Confirm that the aggregated live data is being correctly upserted to the `market_data` table in Supabase.
- [ ] **Task: Update FastAPI Dashboard for Real-time Status**
    - [ ] Modify `src/main_web.py` to reflect the WebSocket connection status and latest live sync timestamp.
- [ ] **Task: Conductor - User Manual Verification 'Phase 3: Integration and Orchestration' (Protocol in workflow.md)**

## Phase 4: Final Validation and Deployment
- [ ] **Task: Final Testing and VPS Deployment Readiness**
    - [ ] Perform long-running stability tests to ensure no connection leaks.
    - [ ] Validate that historical data fetching is still working correctly.
    - [ ] Update documentation for VPS deployment with the new WebSocket client.
- [ ] **Task: Conductor - User Manual Verification 'Phase 4: Final Validation and Deployment' (Protocol in workflow.md)**
