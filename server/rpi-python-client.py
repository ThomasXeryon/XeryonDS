
import asyncio
import websockets
import json
from datetime import datetime

async def connect_to_server():
    rpi_id = "station-8"  # Match the station ID from the database
    uri = f"ws://localhost:5000/rpi/{rpi_id}"
    
    while True:  # Reconnect loop
        try:
            async with websockets.connect(uri) as websocket:
                print(f"[{datetime.now()}] Connected to server as {rpi_id}")
                # Send registration message
                await websocket.send(json.dumps({"rpi_id": rpi_id, "type": "register"}))
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        command = data.get("command", "unknown")
                        direction = data.get("direction", "none")
                        print(f"[{datetime.now()}] Received command: {command}, direction: {direction}")
                        response = {
                            "status": "success",
                            "rpi_id": rpi_id,
                            "message": f"Command '{command}' executed with direction '{direction}'"
                        }
                        await websocket.send(json.dumps(response))
                    except json.JSONDecodeError:
                        print(f"[{datetime.now()}] Invalid message: {message}")
        except Exception as e:
            print(f"[{datetime.now()}] Connection lost: {str(e)}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(connect_to_server())
