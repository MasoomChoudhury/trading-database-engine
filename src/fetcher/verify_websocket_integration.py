import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from fetcher.upstox_websocket import UpstoxWebSocketClient
from fetcher.data_aggregator import MarketDataAggregator

load_dotenv()

async def verify():
    access_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not access_token:
        print("❌ Error: UPSTOX_ACCESS_TOKEN missing in .env")
        return

    aggregator = MarketDataAggregator()
    client = UpstoxWebSocketClient(
        access_token, 
        ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]
    )
    
    def on_data(decoded_data):
        aggregator.process_feed(decoded_data)
        candles = aggregator.get_all_latest_candles('1minute')
        if candles:
            print(f"📡 Real-time Candles: {candles}")
        else:
            # Print keys of decoded data to help debugging
            print(f"📝 Received Data (Keys): {list(decoded_data.get('feeds', {}).keys())}")
            # Print a snippet of one feed
            if decoded_data.get('feeds'):
                first_key = list(decoded_data['feeds'].keys())[0]
                print(f"🔍 Sample Feed [{first_key}]: {decoded_data['feeds'][first_key].keys()}")

    client.add_callback(on_data)
    print("🚀 Starting WebSocket Integration Verification (will run for 30s)...")
    try:
        # Start the client in a background task
        task = asyncio.create_task(client.start())
        # Wait for 30s to see data
        await asyncio.sleep(30)
        # Stop the client
        client.stop()
        await task
        print("\n✅ Verification complete. Check output for real-time candles.")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n❌ Verification Error: {e}")
    finally:
        client.stop()

if __name__ == "__main__":
    asyncio.run(verify())
