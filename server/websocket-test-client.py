
import asyncio
import websockets
import json
from datetime import datetime

# Simple test client that connects to our test server
async def test_websocket():
    urls = [
        "wss://xeryonremotedemostation.replit.app/websocket-test",  # Try standard path first
        "ws://xeryonremotedemostation.replit.app:3333/websocket-test"  # Try custom port
    ]

    for url in urls:
    
    try:
            print(f"[{datetime.now()}] Trying to connect to: {url}")
            async with websockets.connect(url, timeout=10) as ws:
                print(f"[{datetime.now()}] Connected to {url} successfully!")
                
                # Send a test message
                test_message = json.dumps({"type": "test", "message": "Hello from test client"})
                await ws.send(test_message)
                print(f"[{datetime.now()}] Sent test message")
                
                # Wait for response
                response = await ws.recv()
                print(f"[{datetime.now()}] Received: {response}")
                return  # Successfully connected, no need to try other URLs
                
        except Exception as e:
            print(f"[{datetime.now()}] Connection to {url} failed: {str(e)}")
            print(f"[{datetime.now()}] Error type: {type(e).__name__}")
            
    print(f"[{datetime.now()}] All connection attempts failed")

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting WebSocket connection test")
    asyncio.run(test_websocket())
