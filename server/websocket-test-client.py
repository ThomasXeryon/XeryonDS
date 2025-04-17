#!/usr/bin/env python3
"""
WebSocket Test Client for Xeryon Demo Station
- Simulates position updates and camera frames
- For testing purposes
"""

import asyncio
import websockets
import json
import time
import random
import sys
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
STATION_ID = sys.argv[1] if len(sys.argv) > 1 else "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
EPOS_UPDATE_INTERVAL = 0.05  # 20 Hz

# Current position simulation
current_position = 0.0  # in mm
scanning = False
scan_direction = 1
scan_speed = 0.1  # mm per update

async def send_position_updates(websocket):
    """Send simulated position updates."""
    global current_position, scanning, scan_direction
    logger.info(f"Starting position update stream for {STATION_ID}")
    
    while True:
        try:
            # Update position if scanning
            if scanning:
                current_position += scan_direction * scan_speed
                # Bounds checking (-30mm to +30mm)
                if current_position > 30:
                    current_position = 30
                    scan_direction = -1
                elif current_position < -30:
                    current_position = -30
                    scan_direction = 1
            
            # Send position update with timestamp
            position_data = {
                "type": "position_update",
                "rpiId": STATION_ID,
                "epos": current_position,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send(json.dumps(position_data))
            logger.debug(f"Sent position update: {current_position:.3f} mm")
            
            # Wait before next update
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            await asyncio.sleep(1)

async def process_command(command, direction, step_size=None, step_unit=None):
    """Process incoming commands from the UI."""
    global current_position, scanning, scan_direction, scan_speed
    
    logger.info(f"Processing command: {command}, direction: {direction}")
    
    if command == "move" or command == "step":
        scanning = False
        step_value = 1.0  # Default 1mm
        
        if step_size is not None:
            # Convert to mm based on unit
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1000000
        
        # Apply direction
        if direction == "right":
            current_position += step_value
        elif direction == "left":
            current_position -= step_value
            
        # Enforce limits
        current_position = max(-30, min(30, current_position))
        
    elif command == "scan":
        scanning = True
        if direction == "right":
            scan_direction = 1
        elif direction == "left":
            scan_direction = -1
            
    elif command == "stop":
        scanning = False
        
    elif command == "home":
        scanning = False
        current_position = 0.0
        
    elif command == "speed":
        try:
            speed = float(direction)
            scan_speed = speed / 5000  # Scale appropriately
        except ValueError:
            pass
    
    return {
        "status": "success",
        "rpiId": STATION_ID,
        "message": f"Command '{command}' processed"
    }

async def client():
    """Main client function with connection handling."""
    retry_count = 0
    backoff_factor = 1.5
    
    while True:
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            async with websockets.connect(SERVER_URL) as websocket:
                logger.info(f"Connected to WebSocket server as {STATION_ID}")
                
                # Register as a Raspberry Pi client
                registration = {
                    "type": "register",
                    "rpiId": STATION_ID,
                    "connectionType": "combined",
                    "status": "ready",
                    "message": f"RPi {STATION_ID} simulation connected"
                }
                await websocket.send(json.dumps(registration))
                
                # Start position update task
                position_task = asyncio.create_task(send_position_updates(websocket))
                
                # Reset retry on successful connection
                retry_count = 0
                
                # Handle incoming messages
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        if data.get("type") == "command":
                            # Process command
                            cmd = data.get("command", "unknown")
                            direction = data.get("direction", "none")
                            step_size = data.get("stepSize")
                            step_unit = data.get("stepUnit")
                            
                            response = await process_command(cmd, direction, step_size, step_unit)
                            await websocket.send(json.dumps(response))
                            
                        elif data.get("type") == "ping":
                            # Reply with pong
                            pong = {
                                "type": "pong",
                                "timestamp": data.get("timestamp"),
                                "rpiId": STATION_ID
                            }
                            await websocket.send(json.dumps(pong))
                            
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
                        # Don't break on processing errors
                        
                # Clean up tasks if we break out of the loop
                position_task.cancel()
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            
            # Exponential backoff for reconnection
            wait_time = min(60, 1 * (backoff_factor ** retry_count))
            retry_count += 1
            
            logger.info(f"Reconnecting in {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time)

if __name__ == "__main__":
    logger.info(f"Starting WebSocket test client for {STATION_ID}")
    try:
        asyncio.run(client())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")