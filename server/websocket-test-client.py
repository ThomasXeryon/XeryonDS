#!/usr/bin/env python3
"""
WebSocket Test Client for Xeryon Demo Station
- Simulates camera frames and position updates
- Generates test data for UI development and testing
- Maintains persistent connection with automatic reconnection
"""

import asyncio
import websockets
import json
import os
import time
import random
import math
import base64
import sys
from datetime import datetime

# Default RPi ID if none is specified
DEFAULT_RPI_ID = "RPI1"

# Server URL with WebSocket endpoint
SERVER_URL = "ws://localhost:5000/appws"

# Camera frame rate (frames per second)
FRAME_RATE = 10  # 10 FPS
FRAME_INTERVAL = 1.0 / FRAME_RATE

# Position update rate (updates per second)
POSITION_UPDATE_RATE = 20  # 20 updates per second
POSITION_UPDATE_INTERVAL = 1.0 / POSITION_UPDATE_RATE

# Simulated motion parameters
POSITION_MIN = -30.0  # minimum position in mm
POSITION_MAX = 30.0   # maximum position in mm
POSITION_RESOLUTION = 0.001  # position resolution in mm

# Heartbeat interval (in seconds)
HEARTBEAT_INTERVAL = 5

# Positioning simulation variables
current_position = 0.0
target_position = 0.0
velocity = 0.0
acceleration = 0.0
deceleration = 0.0
moving = False
frame_number = 0

# Default test pattern - simple sine wave
def generate_test_pattern(t):
    """Generate a sine wave test pattern"""
    period = 20  # seconds for a complete cycle
    amplitude = 25  # mm (max amplitude within POSITION_MIN/MAX)
    return amplitude * math.sin(2 * math.pi * t / period)

# Function to handle reconnection with exponential backoff
async def connect_with_backoff(rpi_id):
    backoff_time = 1
    max_backoff = 30
    attempt = 1
    
    while True:
        try:
            print(f"Connection attempt {attempt}/{10}, waiting {backoff_time}s...")
            await asyncio.sleep(backoff_time)
            
            ws = await websockets.connect(SERVER_URL)
            print(f"Connected to {SERVER_URL} successfully")
            
            # Register this client with the server
            await ws.send(json.dumps({
                "type": "register",
                "rpiId": rpi_id,
                "connectionType": "combined"
            }))
            print(f"Registered as {rpi_id}")
            
            return ws
            
        except Exception as e:
            print(f"Connection failed: {str(e)}")
            attempt += 1
            backoff_time = min(max_backoff, backoff_time * 1.5 + random.uniform(0, 1))
            if attempt > 10:  # Limit maximum attempts
                print("Maximum connection attempts reached. Exiting.")
                sys.exit(1)

# Generate a dummy image (colored rectangle with timestamp)
def generate_dummy_image():
    global frame_number
    frame_number += 1
    
    # For a real implementation, we'd generate/load an actual image here
    # For this test client, we're returning a placeholder base64 string
    # to simulate camera frames
    
    # This is actually a tiny 1x1 pixel JPEG - in a real app we'd generate
    # a proper test pattern or load an image file
    dummy_image = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9U6KKKADpX//Z"
    
    # Return the base64 data (in real implementation we'd generate this)
    return dummy_image

# Simulate camera frame generation and sending
async def send_camera_frame(websocket, rpi_id):
    global frame_number
    
    # Generate a simulated camera frame
    frame_data = generate_dummy_image()
    
    # Get current timestamp for latency measurement
    timestamp = datetime.now().isoformat()
    
    # Send the frame data to the server
    message = {
        "type": "camera_frame",
        "rpiId": rpi_id,
        "frame": frame_data,
        "frameNumber": frame_number,
        "timestamp": timestamp
    }
    
    await websocket.send(json.dumps(message))
    return True

# Simulate position updates
async def send_position_update(websocket, rpi_id):
    global current_position, target_position, velocity, moving
    
    # Generate timestamp for accurate graphing
    timestamp = datetime.now().isoformat()
    
    # Update simulated position based on time
    t = time.time()
    
    # Use test pattern to determine position
    new_position = generate_test_pattern(t)
    current_position = round(new_position, 3)  # Round to 3 decimal places
    
    # Send position update
    message = {
        "type": "position_update",
        "rpiId": rpi_id,
        "epos": current_position,
        "timestamp": timestamp,
        "velocity": velocity
    }
    
    await websocket.send(json.dumps(message))
    print(f"Position update: {current_position} mm")
    return True

# Heartbeat function to keep connection alive
async def heartbeat(websocket, rpi_id):
    message = {
        "type": "ping",
        "rpiId": rpi_id,
        "timestamp": datetime.now().isoformat()
    }
    
    await websocket.send(json.dumps(message))
    print("Heartbeat sent")
    return True

# Handle incoming messages from the server
async def handle_messages(websocket, rpi_id):
    try:
        message = await websocket.recv()
        data = json.loads(message)
        
        # Process commands from the server
        if data["type"] == "command" and data["rpiId"] == rpi_id:
            command = data["command"]
            direction = data.get("direction")
            step_size = data.get("stepSize", 1.0)
            step_unit = data.get("stepUnit", "mm")
            
            # Convert step size to mm if needed
            if step_unit == "μm":
                step_size_mm = step_size / 1000.0
            elif step_unit == "nm":
                step_size_mm = step_size / 1000000.0
            else:  # Default is mm
                step_size_mm = step_size
            
            # Handle movement commands
            if command == "move":
                if direction == "left":
                    target_position = max(POSITION_MIN, current_position - step_size_mm)
                    moving = True
                    print(f"Moving LEFT by {step_size_mm} mm")
                elif direction == "right":
                    target_position = min(POSITION_MAX, current_position + step_size_mm)
                    moving = True
                    print(f"Moving RIGHT by {step_size_mm} mm")
            
            # Handle home command
            elif command == "home":
                target_position = 0.0
                moving = True
                print("Homing to position 0.0 mm")
            
            # Handle stop command
            elif command == "stop":
                moving = False
                print("Stopping motion")
            
            # Handle acceleration/deceleration settings
            elif command == "set_acceleration":
                acceleration = float(data.get("value", 1000))
                print(f"Setting acceleration to {acceleration}")
            
            elif command == "set_deceleration":
                deceleration = float(data.get("value", 1000))
                print(f"Setting deceleration to {deceleration}")
                
            # Respond with acknowledgment
            await websocket.send(json.dumps({
                "type": "command_ack",
                "rpiId": rpi_id,
                "command": command,
                "status": "executed"
            }))
        
        return True
    
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed by server")
        return False
        
    except Exception as e:
        print(f"Error handling message: {str(e)}")
        return True  # Continue the loop despite error

# Main client function
async def main():
    # Get RPi ID from command line if provided
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPI_ID
    
    print(f"Starting WebSocket test client for {rpi_id}")
    print(f"Connecting to server at {SERVER_URL}")
    
    while True:
        try:
            # Connect to the server with backoff
            ws = await connect_with_backoff(rpi_id)
            
            # Timing variables for rate limiting
            last_frame_time = 0
            last_position_time = 0
            last_heartbeat_time = 0
            
            # Main communication loop
            while True:
                current_time = time.time()
                
                # Handle incoming messages (non-blocking)
                try:
                    # Check if there are messages to process (with a very small timeout)
                    message_received = await asyncio.wait_for(
                        handle_messages(ws, rpi_id),
                        timeout=0.001
                    )
                    if not message_received:
                        raise websockets.exceptions.ConnectionClosed(1000, "Connection reset")
                except asyncio.TimeoutError:
                    # No messages, continue with sending our updates
                    pass
                
                # Send camera frame at the specified rate
                if current_time - last_frame_time >= FRAME_INTERVAL:
                    await send_camera_frame(ws, rpi_id)
                    last_frame_time = current_time
                
                # Send position update at the specified rate
                if current_time - last_position_time >= POSITION_UPDATE_INTERVAL:
                    await send_position_update(ws, rpi_id)
                    last_position_time = current_time
                
                # Send heartbeat periodically
                if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    await heartbeat(ws, rpi_id)
                    last_heartbeat_time = current_time
                
                # Small sleep to prevent CPU spinning
                await asyncio.sleep(0.001)
        
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e}. Attempting to reconnect...")
            await asyncio.sleep(1)
        
        except Exception as e:
            print(f"Unexpected error: {str(e)}. Attempting to reconnect...")
            await asyncio.sleep(2)

# Run the client
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nClient terminated by user")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        sys.exit(1)