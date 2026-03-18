# Specification - Fix Missing Supabase Updates and Dashboard Errors

## Overview
The system is currently failing to update the `market_data` table in Supabase after a sync cycle. While the `app_config` table is updated correctly with the Upstox token, no network requests are being made to the `market_data` table. Additionally, the web dashboard is reporting a `TypeError` related to the charting library.

## Current State
- **Backend:** `src/main_async.py` (or `src/main.py`) runs the sync cycle, but data never reaches the `market_data` table.
- **Supabase Client:** No logged requests to the `market_data` endpoint.
- **Frontend:** Dashboard console reports `TypeError: chart.addCandlestickSeries is not a function` and tracking prevention warnings.

## Functional Requirements
1. **Investigate Backend Sync Loop:** Trace the data flow from `CalculationEngine` to `SupabaseClient.upsert_5min_summary`.
2. **Fix Missing Requests:** Identify and resolve the reason why requests to `market_data` are not being initiated (e.g., silent failures, logic branching errors, or incorrect table mapping).
3. **Resolve Dashboard Charting Error:** Fix the `lightweight-charts` integration in `templates/dashboard.html` to ensure the chart initializes correctly.
4. **Ensure Robust Logging:** Add or improve logging for the Supabase upsert process to make future failures easier to diagnose.

## Acceptance Criteria
- Calculated 5-minute indicator data is consistently upserted to the `market_data` table in Supabase.
- The system logs reflect successful network activity for each sync cycle.
- The web dashboard renders charts without console errors.

## Out of Scope
- Adding new technical indicators.
- Modifying the core `IndicatorEngine` logic (unless required for data formatting).
