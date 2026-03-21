#!/bin/bash
# =============================================================================
# Database Engine — Native (non-Docker) Startup Script
#
# NOTE: For Docker deployments, use ./deploy.sh instead.
#       This script is for development or VPS environments without Docker.
#
# Usage: ./start_sync.sh
# =============================================================================

set -e

cd "$(dirname "$0")"

echo "=============================================="
echo "Database Engine - Market Data Sync"
echo "(Native Python — NOT running in Docker)"
echo "=============================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Install: sudo apt install python3"
    exit 1
fi
python3 --version

# Check .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "WARNING: .env not found. Copy .env.example and fill in credentials."
        echo "  cp .env.example .env"
    fi
fi

# Check dependencies
echo ""
echo "Checking Python dependencies..."
python3 -c "import requests, pandas, supabase, schedule" 2>/dev/null && echo "  All dependencies OK" || {
    echo "  Missing dependencies — installing from requirements.txt..."
    pip3 install -r requirements.txt
}

echo ""
echo "Starting sync engine (Ctrl+C to stop)..."
python3 src/main.py
