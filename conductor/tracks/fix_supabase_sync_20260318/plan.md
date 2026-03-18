# Implementation Plan - Fix Missing Supabase Updates and Dashboard Errors

## Phase 1: Diagnosis & Reproduction
- [ ] **Task: Reproduce Missing Supabase Requests**
    - [ ] Create a reproduction script or unit test in `src/database/test_supabase_sync.py` to simulate a sync cycle.
    - [ ] Confirm that requests to the `market_data` table are NOT being made.
    - [ ] Trace the data flow from the indicator calculation to the upsert call.
- [ ] **Task: Conductor - User Manual Verification 'Phase 1: Diagnosis & Reproduction' (Protocol in workflow.md)**

## Phase 2: Backend Fixes and Logging
- [ ] **Task: Resolve Missing Supabase Upserts**
    - [ ] Fix the logic in `src/main_async.py` (or `src/database/supabase_client.py`) that prevents the `market_data` update.
    - [ ] Ensure any silent exceptions during the upsert process are caught and logged.
    - [ ] Verify that the fix allows data to reach the `market_data` table.
- [ ] **Task: Enhance Sync Logging**
    - [ ] Add detailed logging to `src/main_async.py` to track the start, calculation, and completion of each sync cycle.
    - [ ] Log the status of each Supabase request (Success/Failure/Skipped).
- [ ] **Task: Conductor - User Manual Verification 'Phase 2: Backend Fixes and Logging' (Protocol in workflow.md)**

## Phase 3: Frontend Charting Fix
- [ ] **Task: Resolve Dashboard Charting Error**
    - [ ] Investigate `templates/dashboard.html` to identify the cause of `TypeError: chart.addCandlestickSeries is not a function`.
    - [ ] Fix the `lightweight-charts` initialization and ensure the script is loaded correctly despite tracking prevention.
    - [ ] Verify that the chart renders data correctly in the browser.
- [ ] **Task: Conductor - User Manual Verification 'Phase 3: Frontend Charting Fix' (Protocol in workflow.md)**

## Phase 4: Final Validation
- [ ] **Task: End-to-End System Test**
    - [ ] Run a full sync cycle in a production-like environment.
    - [ ] Confirm data is present in Supabase `market_data` table.
    - [ ] Confirm dashboard shows the live data without console errors.
- [ ] **Task: Conductor - User Manual Verification 'Phase 4: Final Validation' (Protocol in workflow.md)**
