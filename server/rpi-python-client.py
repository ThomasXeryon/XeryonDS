
import asyncio
import websockets
import json
from datetime import datetime
import sys

# Get the station ID from command line arguments or use a default
if len(sys.argv) > 1:
    STATION_ID = sys.argv[1]
else:
    STATION_ID = "RPI1"  # Default ID if none provided

SERVER_URL = "wss://xeryonremotedemostation.replit.app"  # Production URL

async def connect_to_server():
    # The server expects connections to /rpi with no trailing slash
    uri = f"{SERVER_URL}/rpi"
    
    while True:  # Reconnect loop
        try:
            print(f"[{datetime.now()}] Connecting to {uri}...")
            async with websockets.connect(uri) as websocket:
                print(f"[{datetime.now()}] Connected to server as {STATION_ID}")
                # Send registration message
                await websocket.send(json.dumps({"rpi_id": STATION_ID, "type": "register"}))
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        command = data.get("command", "unknown")
                        direction = data.get("direction", "none")
                        print(f"[{datetime.now()}] Received command: {command}, direction: {direction}")
                        
                        # Process the command here (implement your hardware control)
                        # For example, if command is "move", control the actuator
                        
                        # Send back response
                        response = {
                            "status": "success",
                            "rpi_id": STATION_ID,
                            "message": f"Command '{command}' executed with direction '{direction}'"
                        }
                        await websocket.send(json.dumps(response))
                    except json.JSONDecodeError:
                        print(f"[{datetime.now()}] Invalid message: {message}")
        except Exception as e:
            print(f"[{datetime.now()}] Connection error: {str(e)}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    uri = f"{SERVER_URL}/rpi"
    print(f"[{datetime.now()}] Starting RPI WebSocket client for {STATION_ID}")
    print(f"[{datetime.now()}] To use a different ID, run: python rpi-python-client.py YOUR_STATION_ID")
    print(f"[{datetime.now()}] Connecting to server at: {uri}")
    print(f"[{datetime.now()}] Will register with ID: {STATION_ID}")
    asyncio.run(connect_to_server())
