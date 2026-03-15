import sys
import os
import requests

from src.fetcher.upstox_client import UpstoxFetcher

fetcher = UpstoxFetcher()
# Test direct symbol vs ISIN
quote1 = fetcher.get_market_quote(["NSE_EQ|HDFCBANK", "NSE_EQ|INE040A01034"])
print(quote1)
