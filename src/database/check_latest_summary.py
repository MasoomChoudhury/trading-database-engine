import asyncio
import os
import json
from database.supabase_client import RemoteDBWatcher

async def main():
    db = RemoteDBWatcher()
    if not db.supabase:
        print("Error: Supabase client not initialized.")
        return

    try:
        print("Fetching latest summary from 'market_data'...")
        row = db.get_latest_summary()
        if row:
            print("Latest row structure:")
            print(json.dumps(row[0], indent=2))
        else:
            print("No data found in 'market_data'.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
