# Technology Stack

## Core Language
- **Python:** The primary language for data processing, API fetching, and web services.

## Web & API Framework
- **FastAPI:** A modern, high-performance web framework for the dashboard and API endpoints.
- **Uvicorn:** A fast ASGI server for running the FastAPI application.
- **Jinja2:** For template rendering in the dashboard.

## Data Processing & Analysis
- **pandas & pandas-ta:** Essential for handling time-series data and calculating technical indicators (RSI, EMA, etc.).
- **NumPy & SciPy:** For advanced mathematical calculations, including percentiles and potential Black-Scholes modeling.
- **Schedule:** To manage the automated 5-minute data sync cycles.

## Database & Persistence
- **Supabase (PostgreSQL):** The primary remote database for storing market data and configuration.
- **SQLAlchemy:** A powerful SQL toolkit and ORM for database interactions.
- **psycopg2-binary:** A PostgreSQL adapter for Python.

## External Data Ingestion
- **Upstox Python SDK:** To fetch market data, option chains, and Greeks from the Upstox API.
- **Requests & WebSockets:** For handling API calls and potential real-time tick data.

## Utilities & Environment
- **python-dotenv:** To manage environment variables and API keys securely.
- **psutil:** To monitor system resources via the web dashboard.
