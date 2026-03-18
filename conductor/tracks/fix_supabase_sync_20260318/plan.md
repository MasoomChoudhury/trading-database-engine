# Implementation Plan - Fix Missing Supabase Updates and Dashboard Errors

## Objective
Resolve the issue where `market_data` is not updated in Supabase despite `app_config` working correctly, and fix the dashboard charting error.

## Key Files & Context
- `src/main_async.py`: The main sync loop (potentially missing indicators or logic).
- `src/database/supabase_client.py`: Handles Supabase upserts (potential column mismatch or silent failure).
- `src/processor/indicator_engine.py`: Generates the payload for Supabase (potential key mismatch with the dashboard).
- `src/routers/data.py`: Fetches data for the dashboard (expects specific columns).
- `templates/dashboard.html`: Charting implementation (reporting `TypeError`).

## Implementation Steps

### Phase 1: Diagnosis & Reproduction
- [x] **Task 1.1: Investigate Supabase Client Mocking**
    - [x] Add more explicit logging to `RemoteDBWatcher.__init__` to confirm if it's in dry-run mode or connected.
    - [x] Add logging to `upsert_5min_summary` and `set_config` to track which table is being accessed and with what payload.
- [x] **Task 1.2: Trace Data Flow in main_async.py**
    - [x] Add logging before the `upsert_5min_summary` call in `run_5min_sync_cycle` to confirm it is actually reached.
    - [x] Log the keys of the `payload` dictionary to see what's being sent.

### Phase 2: Backend and Supabase Fixes
- [x] **Task 2.1: Align Column Names (ts vs timestamp)**
    - [x] Standardize the timestamp column name. Both `indicator_engine.py` and `supabase_client.py` (querying) should use `timestamp` instead of `ts`, matching the dashboard's expectation in `data.py`.
- [x] **Task 2.2: Fix Payload Structure**
    - [x] Update `generate_5min_sync_payload` in `indicator_engine.py` to include a nested `historical_time_series` object with `open`, `high`, `low`, `close`, `volume` keys, matching `data.py`'s `chart_data()` expectations.
    - [x] Ensure `timestamp` (or `ts`) is correctly populated as a top-level key for indexing/unique constraints.
- [x] **Task 2.3: Enhance main_async.py Indicators**
    - [x] Port the missing indicator calculations from `main.py` to `main_async.py` (e.g., `cpr_status`, `vix_context`, `cost_of_carry`, `true_vwap`, `max_pain`, `pcr`).
    - [x] Ensure the `indicators` dictionary passed to `generate_5min_sync_payload` contains all necessary keys.
- [x] **Task 2.4: Improve UpstoxFetcher Token Management**
    - [x] Update `UpstoxFetcher` to check for a fresh token from Supabase more effectively, potentially refreshing its `access_token` and `headers` during each sync cycle to avoid expiration issues in long-lived processes.

### Phase 3: Frontend Charting Fix
- [x] **Task 3.1: Stabilize Lightweight Charts Integration**
    - [x] In `templates/base.html`, update the `lightweight-charts` script to use a pinned version (e.g., `v4.1.1`).
    - [x] In `templates/dashboard.html`, add defensive checks before calling `addCandlestickSeries`.
    - [x] Verify the property names in the chart initialization (e.g., `background` vs `backgroundColor`).

### Phase 4: Verification & Testing
- [x] **Task 4.1: Automated Unit Tests**
    - [x] Create/Update `src/database/test_supabase_sync.py` to verify the payload structure against the client.
    - [x] Add tests for `CalculationEngine.generate_5min_sync_payload`.
- [x] **Task 4.2: Manual End-to-End Verification**
    - [x] Run `main_async.py` and monitor logs for successful sync messages and network activity.
    - [x] Check the Supabase dashboard to confirm data presence in `market_data`.
    - [x] Open the web dashboard and verify the chart renders correctly.

## Verification & Testing
- **Unit Tests:** `pytest src/database/test_supabase_sync.py`
- **Manual Check:** Access the dashboard at `/` and check browser console for errors.
- **Data Check:** Verify `SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 5` in Supabase.
