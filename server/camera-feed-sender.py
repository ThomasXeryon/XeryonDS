
import asyncio
import websockets
import json
import base64
import cv2
import time
import sys

# Get the station ID from command line arguments or use a default
if len(sys.argv) > 1:
    STATION_ID = sys.argv[1]
else:
    STATION_ID = "RPI1"  # Default ID if none provided

# Only use production URL
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"

async def send_camera_feed():
    # Try different camera ports to find the correct one
    camera_found = False
    for port in range(10):  # Try ports 0-9
        cap = cv2.VideoCapture(port)
        if cap.isOpened():
            ret, test_frame = cap.read()
            if ret:
                print(f"Successfully connected to camera on port {port}")
                camera_found = True
                break
            cap.release()
    
    if not camera_found:
        print("Error: Could not open camera on any port.")
        return
    
    # Set resolution to reduce bandwidth
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Connect to server - only using production URL
    while True:  # Add reconnection loop
        try:
            print(f"Connecting to {SERVER_URL}...")
            async with websockets.connect(SERVER_URL) as websocket:
                print(f"Connected to WebSocket server at {SERVER_URL}")
                
                # Send registration message
                registration_data = {
                    "type": "register",
                    "status": "ready",
                    "message": f"RPi {STATION_ID} online with camera",
                    "rpi_id": STATION_ID
                }
                await websocket.send(json.dumps(registration_data))
                print(f"Sent registration message: {registration_data}")
                
                # Main loop to send camera frames
                while True:
                    # Capture frame with better error handling
                    try:
                        ret, frame = cap.read()
                        if not ret:
                            print("Failed to capture frame, will retry...")
                            await asyncio.sleep(1)
                            continue
                    except Exception as e:
                        print(f"Camera error: {str(e)}, will retry...")
                        await asyncio.sleep(2)
                        continue
                    
                    # Compress and convert frame to JPEG
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    
                    # Convert to base64 string
                    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                    
                    # Send frame to server
                    frame_data = {
                        "type": "camera_frame",
                        "rpi_id": STATION_ID,
                        "frame": jpg_as_text
                    }
                    await websocket.send(json.dumps(frame_data))
                    print(f"Sent frame: {len(jpg_as_text)} bytes")
                    
                    # Process incoming messages
                    try:
                        # Set a short timeout to check for messages without blocking
                        message = await asyncio.wait_for(websocket.recv(), 0.01)
                        data = json.loads(message)
                        command = data.get("command", "unknown")
                        print(f"Received message from server: {data}")
                        
                        # Handle commands here if needed
                    except asyncio.TimeoutError:
                        # No messages received, continue sending frames
                        pass
                    except Exception as e:
                        print(f"Error receiving message: {str(e)}")
                    
                    # Limit frame rate to reduce bandwidth
                    await asyncio.sleep(0.1)  # 10 FPS
                    
        except Exception as e:
            print(f"Connection to {SERVER_URL} failed: {str(e)}")
            print("Connection failed. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        
        # If we get here, connection attempt failed
        print("Connection attempt failed. Retrying in 5 seconds...")
        await asyncio.sleep(5)
        
        # Try reopening the camera if it was closed
        if not cap.isOpened():
            print("Reopening camera...")
            for port in range(10):
                cap = cv2.VideoCapture(port)
                if cap.isOpened():
                    ret, test_frame = cap.read()
                    if ret:
                        print(f"Successfully reconnected to camera on port {port}")
                        break
                cap.release()

if __name__ == "__main__":
    print(f"Starting camera feed from RPi {STATION_ID}")
    print(f"Script configured to connect ONLY to production deployment at {SERVER_URL}")
    try:
        asyncio.run(send_camera_feed())
    except KeyboardInterrupt:
        print("Camera feed stopped by user")
