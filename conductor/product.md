# Initial Concept
A high-performance trading database engine that fetches, processes, and stores market data from Upstox (Indices & Options) into Supabase. It features a Live Indicator Engine (RSI, CPR, GEX, VWAP), a Market Data Warehouse for 1m/5m candles, and a FastAPI dashboard for real-time monitoring and strategy signals.

# Product Definition

## Vision & Goal
To empower intraday traders with a robust, automated market data infrastructure. The engine transforms raw data into high-signal technical and macro indicators (like GEX and CPR), providing a centralized "source of truth" for both live monitoring and historical research.

## Target Audience
- **Intraday Traders:** Seeking real-time edge through advanced signals like Net GEX, CPR relationships, and VWAP status.
- **Quants & Researchers:** Utilizing the high-resolution Market Data Warehouse for strategy backtesting and historical analysis.
- **Dashboard Users:** Needing a centralized, web-based overview of market health and system status.

## Core Features
- **Live Indicator Engine:** Real-time calculation of technical indicators (RSI, EMA, Bollinger Bands) and advanced market metrics (CPR, VWAP, GEX, PCR, Gamma Walls).
- **Market Data Warehouse:** Systematic ingestion and storage of 1-minute and 5-minute candles from Upstox into Supabase, optimized for historical queries.
- **Strategy & Macro Signals:** Generation of automated market context (VIX velocity, institutional context, cost of carry, etc.) to inform trading decisions.
- **Integrated Web Dashboard (FastAPI):** A comprehensive interface for real-time market monitoring, historical data exploration, and administrative configuration (API keys, symbol management).

## Market Data Scope
- **Options Specialty:** Deep focus on Indian Index options (Nifty, Bank Nifty), including live options chains, Greeks, Net GEX, and historical Max Pain shifts.

## Technical Principles
- **Modularity:** Separation of concerns between fetching (Upstox), processing (Indicator Engine), and storage (Supabase/TimescaleDB).
- **Real-time Ingestion:** Transition from polling to a persistent WebSocket-based live data feed for lower latency and improved accuracy.
- **Observability:** Health status monitoring and administrative tools via the web interface.
