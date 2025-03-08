
import asyncio
import websockets
import json
from datetime import datetime
import sys
import traceback

# Get the station ID from command line arguments or use a default
if len(sys.argv) > 1:
    STATION_ID = sys.argv[1]
else:
    STATION_ID = "RPI1"  # Default ID if none provided

# Get server URL - production or development
if len(sys.argv) > 2 and sys.argv[2] == "dev":
    # Use development server with local address
    SERVER_URL = "ws://0.0.0.0:5000"
    print(f"[{datetime.now()}] DEVELOPMENT MODE: Connecting to local server")
else:
    # Production URL
    SERVER_URL = "wss://xeryonremotedemostation.replit.app"
    print(f"[{datetime.now()}] PRODUCTION MODE: Connecting to deployed server")

async def connect_to_server():
    # The server expects connections to /rpi/{rpiId}
    uri = f"{SERVER_URL}/rpi/{STATION_ID}"
    
    while True:  # Reconnect loop
        try:
            print(f"[{datetime.now()}] Connecting to {uri}...")
            
            # Add extra debugging
            print(f"[{datetime.now()}] WebSocket URI: {uri}")
            
            async with websockets.connect(uri, ping_interval=30) as websocket:
                print(f"[{datetime.now()}] Connected to server as {STATION_ID}")
                
                # Send registration message
                registration_message = {
                    "status": "ready", 
                    "message": "RPi device online and ready to accept commands",
                    "type": "register",
                    "rpi_id": STATION_ID
                }
                
                print(f"[{datetime.now()}] Sending registration: {json.dumps(registration_message)}")
                await websocket.send(json.dumps(registration_message))
                
                async for message in websocket:
                    try:
                        print(f"[{datetime.now()}] Received message: {message}")
                        data = json.loads(message)
                        command = data.get("command", "unknown")
                        direction = data.get("direction", "none")
                        print(f"[{datetime.now()}] Processed command: {command}, direction: {direction}")
                        
                        # Process the command here (implement your hardware control)
                        # For example, if command is "move", control the actuator
                        
                        # Send back response
                        response = {
                            "status": "success",
                            "rpi_id": STATION_ID,
                            "message": f"Command '{command}' executed with direction '{direction}'"
                        }
                        print(f"[{datetime.now()}] Sending response: {json.dumps(response)}")
                        await websocket.send(json.dumps(response))
                    except json.JSONDecodeError:
                        print(f"[{datetime.now()}] Invalid message: {message}")
                        
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"[{datetime.now()}] Connection error: server rejected WebSocket connection: {e}. Reconnecting in 5 seconds...")
            print(f"[{datetime.now()}] Error details: {str(e)}")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[{datetime.now()}] Connection error: {str(e)}. Reconnecting in 5 seconds...")
            print(f"[{datetime.now()}] Error traceback: {traceback.format_exc()}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    uri = f"{SERVER_URL}/rpi/{STATION_ID}"
    print(f"[{datetime.now()}] Starting RPI WebSocket client for {STATION_ID}")
    print(f"[{datetime.now()}] To use a different ID, run: python rpi_client.py YOUR_STATION_ID")
    print(f"[{datetime.now()}] To connect to development server: python rpi_client.py YOUR_STATION_ID dev")
    print(f"[{datetime.now()}] Connecting to server at: {uri}")
    asyncio.run(connect_to_server())
