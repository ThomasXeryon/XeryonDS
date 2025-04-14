import asyncio
import websockets
import json
import base64
import cv2
import time
import sys
import random
import math
from datetime import datetime

# Configuration
STATION_ID = "RPI1"
TARGET_FPS = 15
MAX_RECONNECT_ATTEMPTS = 10
CONNECTION_TIMEOUT = 10  # seconds

# Use hostname for websocket connection
SERVER_URL = f"ws://localhost:5000/rpi/{STATION_ID}"

async def rpi_combined_connection(rpi_id, url, max_attempts=MAX_RECONNECT_ATTEMPTS):
    """Establish a COMBINED connection for both camera and control"""
    attempt = 1
    connection_id = f"combined_{int(time.time())}"
    
    while attempt <= max_attempts:
        try:
            print(f"Starting COMBINED connection to: {url} (attempt {attempt}/{max_attempts})")
            
            # Add a unique identifier to prevent caching issues
            combined_url = f"{url}?type=combined&id={connection_id}"
            
            async with websockets.connect(combined_url, ping_interval=None) as websocket:
                # Register as combined connection
                await websocket.send(json.dumps({
                    "type": "register",
                    "rpiId": rpi_id,
                    "connectionType": "combined",
                    "status": "ready",
                    "message": f"RPi {rpi_id} combined connection established"
                }))
                
                print(f"Combined connection established to {url}")
                
                # Start tasks for sending frames and handling commands
                frame_task = asyncio.create_task(send_frames(websocket, rpi_id))
                command_task = asyncio.create_task(handle_commands(websocket, rpi_id))
                
                # Keep the connection alive until it's closed
                try:
                    await asyncio.gather(frame_task, command_task)
                except asyncio.CancelledError:
                    # Cancel tasks if the connection is closed
                    if not frame_task.done():
                        frame_task.cancel()
                    if not command_task.done():
                        command_task.cancel()
                    raise
                
                print("Connection closed, attempting reconnect...")
                return  # Exit on clean close
        
        except Exception as e:
            print(f"Connection error (attempt {attempt}/{max_attempts}): {str(e)}")
            attempt += 1
            # Exponential backoff for reconnection attempts
            await asyncio.sleep(min(30, 2 ** (attempt - 1)))
    
    print("Max reconnection attempts reached, giving up")

async def send_frames(websocket, rpi_id):
    """Send simulated camera frames"""
    frame_count = 0
    position = 10.0  # Start position
    amplitude = 5.0  # Amplitude of the sine wave
    period = 30.0    # Period of the sine wave in seconds
    last_frame_time = time.time()
    
    while True:
        try:
            # Generate a simulated position based on a sine wave
            current_time = time.time()
            elapsed = current_time - last_frame_time
            
            # Rate limit frame sending to target FPS
            frame_interval = 1.0 / TARGET_FPS
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
            
            # Update position with sine wave
            last_frame_time = time.time()
            position = 10.0 + amplitude * math.sin((last_frame_time % period) / period * 2 * math.pi)
            
            # Generate simulated video frame
            frame = create_test_frame(frame_count, position)
            
            # Send position update
            position_message = {
                "type": "position_update",
                "rpiId": rpi_id,
                "epos": round(position, 3),
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(position_message))
            
            # Encode and send frame
            _, buffer = cv2.imencode('.jpg', frame)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            frame_message = {
                "type": "camera_frame",
                "rpiId": rpi_id,
                "frame": jpg_as_text,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(frame_message))
            frame_count += 1
            
            # Send ping message every 5 seconds for latency measurement
            if frame_count % (TARGET_FPS * 5) == 0:
                print(f"Sent ping message for latency measurement")
                ping_message = {
                    "type": "ping",
                    "rpiId": rpi_id,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(ping_message))
            
            # Small delay between frames
            await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"Error in send_frames: {str(e)}")
            break

async def handle_commands(websocket, rpi_id):
    """Handle received command messages"""
    while True:
        try:
            message = await websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "pong":
                print(f"Received pong response on combined connection")
                continue
            
            if data.get("type") == "command":
                command = data.get("command", "unknown")
                direction = data.get("direction", "none")
                step_size = data.get("stepSize")
                
                print(f"Received command: {command}, direction: {direction}, stepSize: {step_size}")
                
                # Send a response back confirming command receipt
                response = {
                    "type": "rpi_response",
                    "rpiId": rpi_id,
                    "status": "success",
                    "message": f"Executed command '{command}' with direction '{direction}'",
                    "command": command,
                    "direction": direction
                }
                await websocket.send(json.dumps(response))
            
        except Exception as e:
            print(f"Error in handle_commands: {str(e)}")
            break

def create_test_frame(frame_number, position):
    """Create a simulated video frame with position information"""
    # Create a black frame
    frame = np.zeros((480, 640, 3), np.uint8)
    
    # Add frame number and position
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    cv2.putText(frame, f"Frame: {frame_number}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Position: {position:.3f} mm", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, timestamp, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    # Add a moving element to simulate motion
    center_x = int(320 + 200 * math.sin((position - 10) / 5 * math.pi))
    cv2.circle(frame, (center_x, 240), 30, (0, 0, 255), -1)
    
    # Draw a grid
    for x in range(0, 641, 80):
        cv2.line(frame, (x, 0), (x, 480), (50, 50, 50), 1)
    for y in range(0, 481, 80):
        cv2.line(frame, (0, y), (640, y), (50, 50, 50), 1)
    
    return frame

async def main():
    """Main entry point"""
    # Use command line argument for RPi ID if provided
    rpi_id = STATION_ID
    if len(sys.argv) > 1:
        rpi_id = sys.argv[1]
    
    server_url = SERVER_URL
    if len(sys.argv) > 2:
        server_url = sys.argv[2]
    
    print(f"Starting RPi client simulation for {rpi_id}")
    
    try:
        await rpi_combined_connection(rpi_id, server_url)
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == "__main__":
    import numpy as np
    asyncio.run(main())