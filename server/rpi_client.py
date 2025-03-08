import asyncio
import websockets
import json
from datetime import datetime
import sys
import traceback
from urllib.parse import urlparse

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
    print(f"[{datetime.now()}] Connecting with URI: {uri}")
    print(f"[{datetime.now()}] Station ID: {STATION_ID}")

    # Debug output
    print(f"[{datetime.now()}] WEBSOCKET DEBUG INFO:")
    print(f"[{datetime.now()}] - Server URL: {SERVER_URL}")
    print(f"[{datetime.now()}] - Station ID: {STATION_ID}")
    print(f"[{datetime.now()}] - Complete URI: {uri}")
    print(f"[{datetime.now()}] - URI components:")
    parsed = urlparse(uri)
    print(f"[{datetime.now()}]   - Scheme: {parsed.scheme}")
    print(f"[{datetime.now()}]   - Netloc: {parsed.netloc}")
    print(f"[{datetime.now()}]   - Path: {parsed.path}")

    while True:  # Reconnect loop
        try:
            print(f"[{datetime.now()}] Connecting to {uri}...")

            # Add more detailed connection debugging
            print(f"[{datetime.now()}] Connection attempt with extra debugging...")

            # Use extra debug parameters
            async with websockets.connect(
                uri,
                extra_headers={
                    'User-Agent': 'RaspberryPi-Client/1.0',
                    'X-Station-ID': STATION_ID
                },
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            ) as websocket:
                print(f"[{datetime.now()}] Connected to server as {STATION_ID}")

                # Send registration message
                registration_message = {
                    "status": "ready", 
                    "message": "RPi device online and ready to accept commands",
                    "type": "register",
                    "rpi_id": STATION_ID
                }
                print(f"[{datetime.now()}] Sending registration message: {registration_message}")
                await websocket.send(json.dumps(registration_message))

                # Process incoming messages
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
                    except json.JSONDecodeError as e:
                        print(f"[{datetime.now()}] Invalid message: {message}")
                        print(f"[{datetime.now()}] Error: {str(e)}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[{datetime.now()}] Connection closed: {str(e)}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except websockets.exceptions.WebSocketException as e:
            print(f"[{datetime.now()}] WebSocket error: {str(e)}. Reconnecting in 5 seconds...")
            traceback.print_exc()  # Print full error for debugging
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error: {str(e)}. Reconnecting in 5 seconds...")
            traceback.print_exc()  # Print full error for debugging
            await asyncio.sleep(5)

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting RPI WebSocket client for {STATION_ID}")
    print(f"[{datetime.now()}] To use a different ID, run: python rpi_client.py YOUR_STATION_ID")
    print(f"[{datetime.now()}] To connect to development server, run: python rpi_client.py YOUR_STATION_ID dev")
    asyncio.run(connect_to_server())