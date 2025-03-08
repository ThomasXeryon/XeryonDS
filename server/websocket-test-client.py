import asyncio
import websockets
import json
from datetime import datetime
import sys

async def rpi_client(rpi_id='RPI1', server_url=None):
    if not server_url:
        # Try different URLs
        urls = [
            f"ws://localhost:5000/rpi/{rpi_id}",         # Local dev
            f"ws://0.0.0.0:5000/rpi/{rpi_id}",          # Direct IP
            f"wss://xeryonremotedemostation.replit.app/rpi/{rpi_id}"  # Production
        ]
    else:
        urls = [server_url]

    print(f"[{datetime.now()}] Starting RPi client simulation for {rpi_id}")

    for url in urls:
        try:
            print(f"[{datetime.now()}] Attempting to connect to: {url}")
            async with websockets.connect(url) as ws:
                print(f"[{datetime.now()}] Connected successfully to {url}")

                # Send initial registration message
                register_msg = {
                    "type": "register",
                    "status": "ready",
                    "message": f"RPi {rpi_id} initialized and ready"
                }
                await ws.send(json.dumps(register_msg))
                print(f"[{datetime.now()}] Sent registration message")

                # Main loop to handle incoming commands
                while True:
                    try:
                        message = await ws.recv()
                        data = json.loads(message)
                        print(f"[{datetime.now()}] Received: {data}")

                        # Handle different command types
                        if data.get("type") == "move":
                            response = {
                                "type": "rpi_response",
                                "status": "ok",
                                "message": f"Moving {data.get('direction', 'unknown')}"
                            }
                        elif data.get("type") == "stop":
                            response = {
                                "type": "rpi_response",
                                "status": "ok",
                                "message": "Movement stopped"
                            }
                        else:
                            response = {
                                "type": "rpi_response",
                                "status": "error",
                                "message": f"Unknown command type: {data.get('type')}"
                            }

                        await ws.send(json.dumps(response))
                        print(f"[{datetime.now()}] Sent response: {response}")

                    except websockets.exceptions.ConnectionClosed:
                        print(f"[{datetime.now()}] Connection closed")
                        break
                    except Exception as e:
                        print(f"[{datetime.now()}] Error handling message: {str(e)}")
                        break

        except Exception as e:
            print(f"[{datetime.now()}] Connection to {url} failed: {str(e)}")
            print(f"[{datetime.now()}] Error type: {type(e).__name__}")
            continue

        print(f"[{datetime.now()}] Connection closed, attempting reconnect...")
        await asyncio.sleep(5)  # Wait before reconnecting

if __name__ == "__main__":
    # Get RPi ID from command line argument or use default
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else 'RPI1'
    server_url = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        asyncio.run(rpi_client(rpi_id, server_url))
    except KeyboardInterrupt:
        print(f"[{datetime.now()}] Shutting down RPi client...")