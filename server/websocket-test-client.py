#!/usr/bin/env python3
"""
WebSocket Test Client for Xeryon Demo Station
- Simulates an RPi client with camera frames and position updates
- Generates dynamic EPOS position data for testing
- Designed for reliable connectivity testing
"""

import asyncio
import websockets
import json
import sys
import os
import time
import random
import base64
from datetime import datetime

# Default RPi ID to use if not specified
DEFAULT_RPI_ID = "RPI1"

# Console colors for better readability
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Error classes for better exception handling
class ConnectionFailed(Exception):
    pass

class FrameGenerationError(Exception):
    pass

# Global variables
frame_number = 0
current_position = 0.0
last_position_update = time.time()
position_direction = 1  # 1 for positive, -1 for negative
moving = False
position_changed = False

# Generate a dummy camera frame as base64 encoded JPEG
def generate_test_frame(rpi_id, width=640, height=480):
    global frame_number
    
    try:
        # Create a simple text overlay with RPi ID and frame number
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Create a base64 encoded data URI
        frame_data = f"data:image/jpeg;base64,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;rpiId={rpi_id};frameNumber={frame_number};timestamp={timestamp}"
        
        # Increment frame number
        frame_number += 1
        
        return frame_data
    except Exception as e:
        print(f"{Colors.FAIL}Error generating test frame: {str(e)}{Colors.ENDC}")
        raise FrameGenerationError(f"Failed to generate test frame: {str(e)}")

# Periodic position update generator
def generate_position_update(rpi_id):
    global current_position, last_position_update, position_direction, moving, position_changed
    
    # Calculate time elapsed since last position update
    now = time.time()
    time_elapsed = now - last_position_update
    last_position_update = now
    
    # Periodically change direction
    if random.random() < 0.02:  # 2% chance per update to change direction
        position_direction = -position_direction
        moving = True
        
    # Periodically stop/start movement
    if random.random() < 0.05:  # 5% chance per update to toggle movement
        moving = not moving
    
    # Update position if moving
    if moving:
        # Calculate new position with random speed variations
        speed = random.uniform(0.01, 0.1)  # mm per update
        position_change = speed * position_direction * time_elapsed * 10
        current_position += position_change
        position_changed = True
        
        # Keep position within reasonable limits (-30 to +30 mm)
        if current_position > 30:
            current_position = 30
            position_direction = -1  # Change direction when hitting limit
        elif current_position < -30:
            current_position = -30
            position_direction = 1  # Change direction when hitting limit
    
    # Timestamp for the position update
    timestamp = datetime.now().isoformat()
    
    # Create the position update message
    position_message = {
        "type": "position_update",
        "rpiId": rpi_id,
        "epos": current_position,
        "timestamp": timestamp,
        "moving": moving
    }
    
    return position_message

# Main WebSocket client function
async def websocket_client(rpi_id):
    # URL with identification for the RPi simulator
    url = f"ws://localhost:5000/rpi/{rpi_id}"
    
    print(f"{Colors.HEADER}Starting WebSocket test client for {rpi_id}{Colors.ENDC}")
    print(f"{Colors.BLUE}Connecting to {url}{Colors.ENDC}")
    
    connection_attempts = 0
    max_attempts = 10
    
    while connection_attempts < max_attempts:
        try:
            async with websockets.connect(url) as websocket:
                print(f"{Colors.GREEN}Connected to server successfully!{Colors.ENDC}")
                
                # Reset connection attempt counter on successful connection
                connection_attempts = 0
                
                # Initialize flags
                global moving, position_changed
                moving = False
                position_changed = False
                
                # Keep track of last frame time to limit frame rate
                last_frame_time = 0
                # Keep track of last position update time
                last_position_time = 0
                
                while True:
                    # Send camera frames at a reasonable rate (e.g., 10 fps)
                    current_time = time.time()
                    
                    # Handle position updates (every 100ms)
                    if current_time - last_position_time >= 0.1:
                        try:
                            position_message = generate_position_update(rpi_id)
                            await websocket.send(json.dumps(position_message))
                            last_position_time = current_time
                            if position_changed:
                                print(f"{Colors.BLUE}Sent position update: {current_position:.3f} mm{Colors.ENDC}")
                                position_changed = False
                        except Exception as e:
                            print(f"{Colors.WARNING}Error sending position update: {str(e)}{Colors.ENDC}")
                    
                    # Handle camera frames (every 100ms = 10fps)
                    if current_time - last_frame_time >= 0.1:
                        try:
                            # Generate and send a test frame
                            frame_data = generate_test_frame(rpi_id)
                            frame_message = {
                                "type": "camera_frame",
                                "rpiId": rpi_id,
                                "frame": frame_data,
                                "frameNumber": frame_number - 1,  # Use the frame number we just incremented
                                "timestamp": datetime.now().isoformat()
                            }
                            await websocket.send(json.dumps(frame_message))
                            last_frame_time = current_time
                            
                            # Print status occasionally (every 10 frames)
                            if frame_number % 10 == 0:
                                print(f"{Colors.GREEN}Sent frame #{frame_number-1}{Colors.ENDC}")
                        except Exception as e:
                            print(f"{Colors.WARNING}Error sending camera frame: {str(e)}{Colors.ENDC}")
                    
                    # Check for incoming messages (with a short timeout)
                    try:
                        # Use a very short timeout to avoid blocking the loop
                        websocket.recv_timeout = 0.01
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.01)
                        
                        # Process incoming message
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            
                            if msg_type == "command":
                                command = data.get("command", "")
                                print(f"{Colors.BLUE}Received command: {command}{Colors.ENDC}")
                                
                                # Handle movement commands
                                if command == "move":
                                    direction = data.get("direction", "")
                                    step_size = data.get("stepSize", 0.1)
                                    step_unit = data.get("stepUnit", "mm")
                                    
                                    # Convert step size to mm if needed
                                    if step_unit == "μm":
                                        step_size /= 1000
                                    elif step_unit == "nm":
                                        step_size /= 1000000
                                    
                                    # Update position
                                    if direction == "left":
                                        current_position -= step_size
                                    elif direction == "right":
                                        current_position += step_size
                                    
                                    # Keep position within limits
                                    if current_position > 30:
                                        current_position = 30
                                    elif current_position < -30:
                                        current_position = -30
                                    
                                    print(f"{Colors.GREEN}Position now: {current_position:.3f} mm{Colors.ENDC}")
                                
                                # Handle home command
                                elif command == "home":
                                    current_position = 0
                                    print(f"{Colors.GREEN}Homed to position: 0.000 mm{Colors.ENDC}")
                                
                                # Handle stop command
                                elif command == "stop":
                                    moving = False
                                    print(f"{Colors.WARNING}Stopped movement{Colors.ENDC}")
                            
                            elif msg_type == "ping":
                                # Respond to ping with a pong to keep the connection alive
                                pong_message = {
                                    "type": "pong",
                                    "rpiId": rpi_id,
                                    "timestamp": datetime.now().isoformat()
                                }
                                await websocket.send(json.dumps(pong_message))
                        except json.JSONDecodeError:
                            print(f"{Colors.WARNING}Received non-JSON message: {message}{Colors.ENDC}")
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                        # Timeout is expected as we're using a very short timeout
                        # Just continue the loop
                        pass
                    
                    # Small sleep to prevent CPU from maxing out
                    await asyncio.sleep(0.01)
                    
        except (websockets.exceptions.ConnectionClosed, 
                websockets.exceptions.InvalidStatusCode,
                ConnectionRefusedError,
                OSError) as e:
            connection_attempts += 1
            print(f"{Colors.FAIL}Connection failed (attempt {connection_attempts}/{max_attempts}): {str(e)}{Colors.ENDC}")
            # Use exponential backoff for reconnection
            backoff_time = min(2 ** connection_attempts, 60)
            print(f"{Colors.WARNING}Retrying in {backoff_time} seconds...{Colors.ENDC}")
            await asyncio.sleep(backoff_time)
    
    print(f"{Colors.FAIL}Failed to connect after {max_attempts} attempts. Exiting.{Colors.ENDC}")

async def main():
    # Get the RPi ID from command line if provided, otherwise use default
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RPI_ID
    
    try:
        await websocket_client(rpi_id)
    except KeyboardInterrupt:
        print(f"{Colors.BLUE}WebSocket test client stopped by user.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Unexpected error: {str(e)}{Colors.ENDC}")
        raise

if __name__ == "__main__":
    asyncio.run(main())