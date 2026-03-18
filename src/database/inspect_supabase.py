import asyncio
import os
import json
from database.supabase_client import RemoteDBWatcher

async def main():
    db = RemoteDBWatcher()
    if not db.supabase:
        print("Error: Supabase client not initialized. Check .env")
        return

    # Try to fetch one row from 'market_data' to see its structure
    try:
        response = db.supabase.table('market_data').select('*').limit(1).execute()
        if response.data:
            print("Successfully fetched row from 'market_data':")
            print(json.dumps(response.data[0], indent=2))
        else:
            print("No rows found in 'market_data' table.")
    except Exception as e:
        print(f"Error fetching from 'market_data': {e}")

    # Check for 'market_data_5min' table too
    try:
        response = db.supabase.table('market_data_5min').select('*').limit(1).execute()
        if response.data:
            print("\nSuccessfully fetched row from 'market_data_5min':")
            print(json.dumps(response.data[0], indent=2))
        else:
            print("\nNo rows found in 'market_data_5min' table.")
    except Exception as e:
        print(f"Error fetching from 'market_data_5min': {e}")

if __name__ == "__main__":
    asyncio.run(main())
