
import asyncio
import websockets
import json
from datetime import datetime
import sys

# Test WebSocket URI 
TEST_SERVER_URL = "wss://xeryonremotedemostation.replit.app" 

async def test_connection():
    # Simple test endpoint
    uri = f"{TEST_SERVER_URL}/ws"
    
    print(f"[{datetime.now()}] Testing WebSocket connection to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"[{datetime.now()}] Successfully connected to test endpoint!")
            
            # Send a test message
            test_message = json.dumps({"type": "test", "message": "Hello from test client"})
            await websocket.send(test_message)
            print(f"[{datetime.now()}] Sent test message")
            
            # Wait for response
            response = await websocket.recv()
            print(f"[{datetime.now()}] Received: {response}")
            
            # Keep connection alive for a bit
            print(f"[{datetime.now()}] Keeping connection alive for 10 seconds...")
            await asyncio.sleep(10)
            
            print(f"[{datetime.now()}] Test completed successfully!")
    except Exception as e:
        print(f"[{datetime.now()}] Test connection error: {str(e)}")

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting WebSocket connection test")
    asyncio.run(test_connection())
