
import asyncio
import websockets
import json
from datetime import datetime

# Simple test client that connects to our test server
async def test_websocket():
    print(f"[{datetime.now()}] Starting WebSocket connection test")
    
    # Test connections to try (local, deployed, direct port)
    urls = [
        "ws://localhost:3333/websocket-test",       # Local dev with direct port
        "ws://0.0.0.0:3333/websocket-test",         # Direct IP access
        f"ws://{asyncio.get_event_loop().run_in_executor(None, lambda: __import__('os').environ.get('REPL_SLUG', 'localhost'))}.replit.dev:3333/websocket-test"  # Replit URL with port
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
                return  # Successfully connected, no need to try other URLs
                
        except Exception as e:
            print(f"[{datetime.now()}] Connection to {url} failed: {str(e)}")
            print(f"[{datetime.now()}] Error type: {type(e).__name__}")
            
    print(f"[{datetime.now()}] All connection attempts failed")

if __name__ == "__main__":
    asyncio.run(test_websocket())
