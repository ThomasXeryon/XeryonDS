#!/usr/bin/env python3
"""
RPi WebSocket Test Client for Xeryon Demo Station
- Simulates RPi client for testing
- Sends position updates and camera frames
- Handles commands with proper unit conversion
"""

import asyncio
import websockets
import json
import base64
from datetime import datetime
import sys
import os
import time
import random
import logging

# ===== CONFIGURATION =====
STATION_ID = sys.argv[1] if len(sys.argv) > 1 else "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
EPOS_UPDATE_INTERVAL = 0.1  # 100ms position update interval
VIDEO_FRAME_INTERVAL = 0.2  # 200ms frame interval (5 FPS for testing)

# ===== LOGGING SETUP =====
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RPiSimulator")

# ===== GLOBAL STATE =====
current_position = 0.0  # Initial position in mm
target_position = None  # Target position for moves
scanning_direction = None  # Direction for continuous scanning
current_frame_number = 0
shutdown_requested = False
scanning_speed = 0.5  # mm per update interval

# ===== COMMAND PROCESSING =====
async def handle_command(command_data):
    """Process incoming commands with proper unit handling"""
    global current_position, target_position, scanning_direction
    
    command_type = command_data.get("command", "unknown")
    direction = command_data.get("direction", "none")
    step_size = command_data.get("stepSize")
    step_unit = command_data.get("stepUnit", "mm")
    
    # Log the received command
    logger.info(f"Received command: {command_type}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}")
    
    # Handle step unit conversion
    if step_size is not None and step_unit:
        # Convert to mm (standard unit)
        step_value = float(step_size)
        if step_unit == "µm":  # micro-meters (note the correct unicode character)
            step_value /= 1000
        elif step_unit == "nm":  # nano-meters
            step_value /= 1_000_000
            
        logger.info(f"Converted step: {step_size} {step_unit} = {step_value} mm")
    else:
        step_value = 1.0  # Default 1mm
    
    # Process the command
    if command_type == "step":
        # Apply direction
        if direction == "right":
            current_position += step_value
        elif direction == "left":
            current_position -= step_value
        elif direction == "up":  # Not used in single-axis setup
            pass
        elif direction == "down":  # Not used in single-axis setup
            pass
            
        # Limit position to reasonable range (-30mm to +30mm)
        current_position = max(-30, min(30, current_position))
        target_position = None  # Step completed, no further movement
        scanning_direction = None  # Stop any scanning
        
    elif command_type == "move":
        # Start continuous movement
        scanning_direction = direction
        
    elif command_type == "move_right":
        scanning_direction = "right"
        
    elif command_type == "move_left":
        scanning_direction = "left"
        
    elif command_type == "stop":
        scanning_direction = None
        target_position = None
        
    elif command_type == "home":
        current_position = 0.0
        scanning_direction = None
        target_position = None
    
    return {
        "type": "command_response",
        "status": "success",
        "command": command_type,
        "rpiId": STATION_ID,
        "epos": current_position,
        "timestamp": datetime.now().isoformat()
    }

# ===== UPDATE FUNCTIONS =====
async def update_position():
    """Update position based on current state and send position updates"""
    global current_position, scanning_direction
    
    if scanning_direction == "right":
        current_position += scanning_speed
        if current_position > 30:  # Limit range
            current_position = 30
            scanning_direction = None  # Stop at the end
    elif scanning_direction == "left":
        current_position -= scanning_speed
        if current_position < -30:  # Limit range
            current_position = -30
            scanning_direction = None  # Stop at the end
    
    # Add a small random fluctuation for realism
    jitter = random.uniform(-0.001, 0.001)
    display_position = current_position + jitter
    
    return {
        "type": "position_update",
        "rpiId": STATION_ID,
        "epos": round(display_position, 3),
        "timestamp": datetime.now().isoformat(),
        "velocity": 0 if scanning_direction is None else (scanning_speed if scanning_direction == "right" else -scanning_speed)
    }

async def generate_camera_frame():
    """Generate a minimal camera frame for testing"""
    global current_frame_number
    
    # Create a tiny 1x1 JPEG image (smallest possible valid JPEG)
    # This is just for testing; a real implementation would use a camera
    tiny_jpeg = '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9U6KKKADpX//Z'
    
    current_frame_number += 1
    
    return {
        "type": "camera_frame",
        "rpiId": STATION_ID,
        "frame": tiny_jpeg,  # Base64 encoded JPEG data
        "frameNumber": current_frame_number,
        "timestamp": datetime.now().isoformat()
    }

# ===== MAIN CONNECTION HANDLING =====
async def heartbeat_loop(websocket):
    """Send periodic heartbeats to keep connection alive"""
    while not shutdown_requested:
        try:
            await websocket.send(json.dumps({
                "type": "heartbeat",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }))
            logger.debug("Heartbeat sent")
            await asyncio.sleep(5.0)  # 5 second interval
        except Exception as e:
            logger.error(f"Heartbeat error: {str(e)}")
            break

async def position_update_loop(websocket):
    """Send continuous position updates"""
    while not shutdown_requested:
        try:
            position_data = await update_position()
            await websocket.send(json.dumps(position_data))
            print(f"Position update: {position_data['epos']} mm")
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            break

async def camera_frame_loop(websocket):
    """Send periodic camera frames"""
    while not shutdown_requested:
        try:
            frame_data = await generate_camera_frame()
            await websocket.send(json.dumps(frame_data))
            await asyncio.sleep(VIDEO_FRAME_INTERVAL)
        except Exception as e:
            logger.error(f"Camera frame error: {str(e)}")
            break

async def main():
    """Main connection handler"""
    global shutdown_requested
    
    url = SERVER_URL
    logger.info(f"Connecting to {url} as {STATION_ID}")
    
    connection_attempts = 0
    max_attempts = 10
    
    while connection_attempts < max_attempts and not shutdown_requested:
        try:
            connection_attempts += 1
            logger.info(f"Connection attempt {connection_attempts}/{max_attempts}")
            
            async with websockets.connect(url) as websocket:
                # Register with server as a combined connection
                await websocket.send(json.dumps({
                    "type": "register",
                    "rpiId": STATION_ID,
                    "connectionType": "combined"
                }))
                
                logger.info(f"Connected to server as RPi {STATION_ID}")
                
                # Start update loops
                tasks = [
                    asyncio.create_task(heartbeat_loop(websocket)),
                    asyncio.create_task(position_update_loop(websocket)),
                    asyncio.create_task(camera_frame_loop(websocket))
                ]
                
                # Handle incoming commands
                try:
                    while not shutdown_requested:
                        message = await websocket.recv()
                        try:
                            data = json.loads(message)
                            
                            if data.get("type") == "command":
                                response = await handle_command(data)
                                if response:
                                    await websocket.send(json.dumps(response))
                                    
                            elif data.get("type") == "ping":
                                # Respond to ping with pong
                                await websocket.send(json.dumps({
                                    "type": "pong",
                                    "timestamp": data.get("timestamp"),
                                    "rpiId": STATION_ID
                                }))
                                
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON: {message}")
                            
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed, attempting to reconnect...")
                
                # Cancel all tasks when connection is closed
                for task in tasks:
                    task.cancel()
                
                # Wait for tasks to complete
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except asyncio.CancelledError:
                    pass
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            
        # Wait before retrying
        if not shutdown_requested and connection_attempts < max_attempts:
            await asyncio.sleep(5)
    
    if connection_attempts >= max_attempts:
        logger.error(f"Failed to connect after {max_attempts} attempts")

# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        shutdown_requested = True