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

                # Simulate sending camera frames
                frame_count = 0
                while True:
                    try:
                        # Create a simulated frame (just a counter for testing)
                        frame_data = {
                            "type": "camera_frame",
                            "rpiId": rpi_id,
                            "frame": "SGVsbG8gV29ybGQ="  # Base64 "Hello World" as test data
                        }
                        await ws.send(json.dumps(frame_data))
                        
                        # Also send position data update (EPOS value)
                        # Send a sine wave oscillation for interesting movement
                        import math
                        position_value = round(10.0 + 5.0 * math.sin(frame_count * 0.2), 3)
                        position_data = {
                            "type": "position_update",
                            "rpiId": rpi_id,
                            "epos": position_value
                        }
                        await ws.send(json.dumps(position_data))
                        
                        frame_count += 1
                        print(f"[{datetime.now()}] Sent frame #{frame_count} with position {position_value}")

                        # Process any incoming messages
                        try:
                            message = await asyncio.wait_for(ws.recv(), 0.1)
                            data = json.loads(message)
                            print(f"[{datetime.now()}] Received: {data}")
                        except asyncio.TimeoutError:
                            # No messages received, continue sending frames
                            pass
                        except Exception as e:
                            print(f"[{datetime.now()}] Error receiving message: {str(e)}")

                        # Wait before sending next frame
                        await asyncio.sleep(1)  # Send a frame every second

                    except websockets.exceptions.ConnectionClosed:
                        print(f"[{datetime.now()}] Connection closed")
                        break
                    except Exception as e:
                        print(f"[{datetime.now()}] Error in main loop: {str(e)}")
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