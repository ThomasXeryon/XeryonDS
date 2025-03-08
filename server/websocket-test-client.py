
import asyncio
import websockets
import json
from datetime import datetime

# Simple test client that connects to our test server
async def test_websocket():
    # Try both the full URL and a direct connection to the port
    urls = [
        "wss://xeryonremotedemostation.replit.app", 
        "ws://xeryonremotedemostation.replit.app:3333"
    ]
    
    for url in urls:
        try:
            print(f"[{datetime.now()}] Trying to connect to: {url}")
            async with websockets.connect(url) as ws:
                print(f"[{datetime.now()}] Connected to {url} successfully!")
                
                # Send a test message
                test_message = json.dumps({"type": "test", "message": "Hello from test client"})
                await ws.send(test_message)
                print(f"[{datetime.now()}] Sent test message")
                
                # Wait for response
                response = await ws.recv()
                print(f"[{datetime.now()}] Received: {response}")
                
                # Success with this URL, no need to try others
                return
                
        except Exception as e:
            print(f"[{datetime.now()}] Connection to {url} failed: {str(e)}")
    
    print(f"[{datetime.now()}] All connection attempts failed")

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting WebSocket connection test")
    asyncio.run(test_websocket())
