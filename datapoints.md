# Data Points & Agent Integration Strategy

This document outlines all the exact data points fetched and calculated by the Data Engine, and stored within your Supabase `market_data` table. It distinguishes between **Live Intraday** metrics and **Contextual (Historical)** metrics mathematically compared against the live data.

You can use this list to decide which subset of variables should be fed into specific sub-agents (e.g., Institutional Flow Agent, Retail Liquidity Agent, Options Pricing Agent).

---

## 1. Core Price & Index Mechanics

### Live Data
- **`spot_nifty_ohlcv`**: The raw 5-minute candle for the NSE Nifty 50 Index.
- **`futures_nifty_ohlcv`**: The raw 5-minute candle for the active Front-Month Nifty Futures contract.
- **`synthetic_nifty_ohlc`**: A dynamically blended candle designed for zero-spread backtesting.

### Historical Context
- **`key_intraday_levels`**: 
  - Previous Day High (PDH) & Previous Day Low (PDL)
  - *Comparison:* Percentage distance from the Live Spot price to PDH/PDL (useful for breakout models).
- **`cpr_status`**: 
  - Central Pivot Range calculated from the previous day's (H+L+C).
  - *Comparison:* Is Live Price **Above**, **Below**, or **Inside** the CPR? What is the *width* of the CPR (Narrow = Trend Day, Wide = Range Day)?
- **`opening_range_status`**: 
  - Top and bottom of the first 15-minute trading block today.
  - *Comparison:* Is Live Price breaking above/below the Opening Range peak?

---

## 2. Options Architecture (The AI Decision Matrix)

### Live Data
- **`options_decision_matrix`**: An array of 22 specific Option Contracts (Calls and Puts) mapped precisely to `ATM ± 5 Strikes`. For each contract, the agent receives:
  - `ltp` (Last Traded Price)
  - `intrinsic_value` vs `time_value`
  - **Live Greeks**: `delta`, `theta`, `gamma`, `vega`, `iv`
  - **Live Liquidity**: `volume`, `open_interest`, `oi_day_high`
  - `candles_5m`: Intraday OHLCV array for that specific strike today.
- **`term_structure_liquidity`**: 
  - Market Quote aggregated limits (Bid/Ask spread and volume) for the ATM strikes across the **Next 5 Expiries** to detect timeline rollovers.
- **`net_gex`**: Total Gamma Exposure calculated dynamically across the entire active Option Chain.

### Historical Context / Flow Analysis
- **`gamma_walls`**: 
  - The exact strikes with the Highest Call OI (Ceiling) and Highest Put OI (Floor). 
  - *Comparison:* Distance from Live Spot to the Call Wall and Put Wall (+ semantic "Pinned", "Approaching Resistance" warning signals).
- **`gamma_flip_point`**: 
  - The exact strike where Dealer Net Gamma shifts from positive (mean-reverting) to negative (trending).
- **`max_pain_strike`**: 
  - Live Mathematical Max Pain strike.
  - *Comparison (Daily Shift):* Compares the Live Max Pain against the Max Pain from exactly 24 hours and 48 hours ago (e.g., "Upward Floor Shift" or "Stable Floor").
- **`options_pcr`**: 
  - Total Put OI / Total Call OI.
  - *Comparison (20-Day Statistical Percentile):* Compares the Live PCR against the historical 20-day array to signal if it is historically over-leveraged on calls or puts (Scale of 0 to 100).

---

## 3. Institutional & Smart Money Context

### Live Data
- **`market_internals`**: A semantic string interpreting if Spot Direction perfectly aligns with Gamma Direction (e.g., "Aligned Flow (Bullish)").
- **`heavyweight_vs_vwap`**: 
  - Analyzes the Top 5 heavyweights (HDFC, RELIANCE, ICICI, INFY, TCS).
  - *Comparison:* Checks if these individual stocks are trading above or below their own intraday VWAP to calculate a "Heavyweight Bias Score".
- **`momentum_burst`**: 
  - *Comparison:* Is the current 5-min volume strictly greater than the 20-period moving average of volume?

### Historical Context / VWAP Tracking
- **`true_vwap`**: 
  - VWAP calculated strictly on the active Nifty Future contract (since indices don't have true volume).
  - *Comparison:* Live Price vs. True VWAP. Signals extreme distances (> 15 points) as Trend Extensions vs. Mean Reversions.
- **`institutional_vwap_context` (BTST Anchor)**: 
  - Anchors the VWAP starting from 15:00 of the *Previous Trading Day*.
  - *Comparison:* Identifies how far Extended the market is from the overnight institutional filling price, predicting "High Reversion Probabilities".
- **`cost_of_carry` (Futures Premium/Discount)**: 
  - Live difference between Futures and Spot price.
  - *Comparison 1 (15m Delta):* How fast has the premium expanded or contracted in the last 15 minutes? (Institutional buying/selling velocity).
  - *Comparison 2 (20-Day Baseline):* Compares the Live Premium against the 1-Month Simple Moving Average of the Premium to detect structural baseline shifts.

---

## 4. Volatility Index (India VIX)

### Live Data
- **`live_vix`**: The exact current reading of the India VIX.

### Historical Context
- **`vix_context`**: 
  - *Comparison (5-Day Trend):* Uses the last 5 days of VIX closes to output a semantic trend (e.g., "Expanding", "Crushing").
  - *Comparison (20-Day Percentile):* Calculates the IV Rank mathematically against the last 20 days. Tells the agent if premiums are historically "Expensive" or "Cheap".
  - *Comparison (Intraday Velocity):* Detects sudden % spikes in the VIX from the day's open.

---

## Suggested Agent Routing Summary

If you are orchestrating a Multi-Agent Swarm, consider routing the payload like this:

1. **Macro / Context Agent**: Feed it `vix_context`, `cost_of_carry`, `institutional_vwap_context`, `cpr_status`, and `max_pain_strike` shift. Let it dictate the Overarching Trend (Bullish, Bearish, Rangebound).
2. **Options Pricing & Execution Agent**: Feed it the `options_decision_matrix`, `gamma_walls`, `gamma_flip_point`, and `true_vwap` distance. Let it select the exact Strike Price + Direction (CE/PE) based on IV Rank and distance to the nearest wall.
3. **Retail Flow (Contrarian) Agent**: Feed it `options_pcr` (specifically the 20-Day Percentile), `momentum_burst`, and `term_structure_liquidity`. Let it determine if the crowd is trapped and a squeeze is imminent.
