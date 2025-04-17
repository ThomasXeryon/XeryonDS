
#!/usr/bin/env python3
import asyncio
import websockets
import json
import base64
import cv2
import time
import sys
import random
from datetime import datetime

# Constants
WEBSOCKET_URL = "ws://localhost:5000/rpi/"
CAMERA_FPS = 30
POSITION_UPDATE_INTERVAL = 0.1  # 100ms between position updates

async def send_camera_frame(websocket, cap):
    ret, frame = cap.read()
    if not ret:
        return
    
    # Encode frame as JPEG
    _, buffer = cv2.imencode('.jpg', frame)
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    
    # Create frame message
    frame_message = {
        "type": "camera_frame",
        "frame": f"data:image/jpeg;base64,{jpg_as_text}",
        "timestamp": datetime.now().isoformat(),
    }
    
    await websocket.send(json.dumps(frame_message))

async def send_position_update(websocket):
    # Simulate position data (oscillating between -100 and 100)
    position = 100 * math.sin(time.time())
    
    position_message = {
        "type": "position",
        "position": position,
        "timestamp": datetime.now().isoformat(),
    }
    
    await websocket.send(json.dumps(position_message))

async def heartbeat(websocket):
    while True:
        try:
            ping_message = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(ping_message))
            await asyncio.sleep(1)
        except:
            break

async def handle_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received message: {data}")
            
            # Handle command messages
            if data.get("type") == "command":
                response = {
                    "type": "command_response",
                    "status": "success",
                    "command": data.get("command"),
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(response))
        except Exception as e:
            print(f"Error handling message: {e}")
            break

async def main():
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else "RPI1"
    url = f"{WEBSOCKET_URL}{rpi_id}"
    
    while True:
        try:
            print(f"Connecting to {url}...")
            async with websockets.connect(url) as websocket:
                print("Connected!")
                
                # Send registration message
                reg_message = {
                    "type": "register",
                    "connectionType": "combined"
                }
                await websocket.send(json.dumps(reg_message))
                
                # Initialize camera
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(-1)  # Try default camera
                
                if not cap.isOpened():
                    print("Warning: No camera available, will simulate camera feed")
                    # Create a black frame
                    frame = np.zeros((480, 640, 3), np.uint8)
                    cap = type('DummyCap', (), {
                        'read': lambda self: (True, frame),
                        'isOpened': lambda self: True
                    })()
                
                # Start heartbeat
                heartbeat_task = asyncio.create_task(heartbeat(websocket))
                message_handler = asyncio.create_task(handle_messages(websocket))
                
                last_frame_time = 0
                last_position_time = 0
                
                while True:
                    current_time = time.time()
                    
                    # Send camera frame if interval elapsed
                    if current_time - last_frame_time >= 1.0/CAMERA_FPS:
                        await send_camera_frame(websocket, cap)
                        last_frame_time = current_time
                    
                    # Send position update if interval elapsed
                    if current_time - last_position_time >= POSITION_UPDATE_INTERVAL:
                        await send_position_update(websocket)
                        last_position_time = current_time
                    
                    await asyncio.sleep(0.001)  # Small sleep to prevent CPU hogging
                
        except Exception as e:
            print(f"Connection error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    import math
    import numpy as np
    asyncio.run(main())
