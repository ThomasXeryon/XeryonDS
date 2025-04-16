#!/usr/bin/env python3
"""
Binary WebSocket Test Client
- Tests binary frame transmission for the Xeryon demo station
- Simulates camera frames using binary WebSocket frames
- Validates end-to-end binary transmission path
"""

import asyncio
import websockets
import time
import random
import struct
import argparse
import logging
import signal
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("BinaryTest")

# Default configuration
DEFAULT_SERVER_URL = "ws://localhost:5000/rpi/{rpi_id}"
DEFAULT_RPI_ID = "RPI1"
FRAME_INTERVAL = 0.2  # 5 FPS for testing
FRAME_HEADER_FORMAT = "<4sII"  # format: 4-char station ID, uint32 frame number, uint32 timestamp

# Global state
shutdown_requested = False

def create_binary_test_frame(frame_number, rpi_id):
    """Create a test binary frame with header and fake JPEG data."""
    # Create the header with RPI ID, frame number and timestamp
    timestamp = int(time.time() * 1000)  # Milliseconds
    header = struct.pack(FRAME_HEADER_FORMAT,
                        rpi_id.encode()[:4].ljust(4),  # Force 4 chars
                        frame_number,
                        timestamp)
    
    # Create fake JPEG data - for testing only
    # In a real scenario, this would be actual JPEG bytes
    # Here we just create a pattern that includes the frame number
    frame_text = f"TESTFRAME_{frame_number}_{timestamp}".encode()
    # Pad with enough data to make it look like a real image (30KB)
    padding = b'\x00' * (30 * 1024 - len(frame_text))
    fake_jpeg = frame_text + padding
    
    # Combine header and fake JPEG data
    binary_data = header + fake_jpeg
    
    return binary_data

async def register_with_server(websocket, rpi_id):
    """Register with the server as a combined connection."""
    register_message = {
        "type": "register",
        "rpiId": rpi_id,
        "connectionType": "combined"
    }
    
    await websocket.send(str(register_message).replace("'", '"'))
    logger.info(f"Registered with server as {rpi_id} with combined connection type")

async def send_binary_frames(websocket, rpi_id):
    """Send binary frames to the server at regular intervals."""
    frame_number = 0
    
    while not shutdown_requested:
        try:
            # Create a binary test frame
            binary_data = create_binary_test_frame(frame_number, rpi_id)
            
            # Send the binary data
            await websocket.send(binary_data)
            
            if frame_number % 10 == 0:
                logger.info(f"Sent binary frame #{frame_number}, size: {len(binary_data)} bytes")
            
            frame_number += 1
            
            # Wait for next frame interval
            await asyncio.sleep(FRAME_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error sending binary frame: {e}")
            await asyncio.sleep(1)

async def send_position_updates(websocket, rpi_id):
    """Send simulated position updates."""
    position = 0.0
    direction = 1  # 1 = increasing, -1 = decreasing
    
    while not shutdown_requested:
        try:
            # Simple oscillating position between -30mm and +30mm
            position += direction * 0.2
            
            # Reverse direction at limits
            if position > 30:
                position = 30
                direction = -1
            elif position < -30:
                position = -30
                direction = 1
            
            # Create position update message
            message = {
                "type": "position_update",
                "rpiId": rpi_id,
                "epos": round(position, 3)
            }
            
            # Send message
            await websocket.send(str(message).replace("'", '"'))
            
            # Wait before sending next update
            await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Error sending position update: {e}")
            await asyncio.sleep(1)

async def send_heartbeats(websocket, rpi_id):
    """Send periodic heartbeats to keep the connection alive."""
    while not shutdown_requested:
        try:
            # Create heartbeat message
            message = {
                "type": "ping",
                "rpiId": rpi_id,
                "timestamp": datetime.now().isoformat()
            }
            
            # Send message
            await websocket.send(str(message).replace("'", '"'))
            logger.debug("Sent heartbeat ping")
            
            # Wait before sending next heartbeat
            await asyncio.sleep(5)
        
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
            await asyncio.sleep(1)

async def message_handler(websocket, rpi_id):
    """Handle incoming messages from the server."""
    while not shutdown_requested:
        try:
            message = await websocket.recv()
            
            # Simple message logging - assuming text messages
            if isinstance(message, str):
                logger.debug(f"Received text message: {message[:100]}")
            else:
                logger.debug(f"Received binary message of {len(message)} bytes")
        
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            break

async def run_binary_test_client(server_url, rpi_id):
    """Run the binary WebSocket test client."""
    url = server_url.format(rpi_id=rpi_id)
    logger.info(f"Connecting to {url}")
    
    try:
        async with websockets.connect(url) as websocket:
            logger.info("Connected to server")
            
            # Register with the server
            await register_with_server(websocket, rpi_id)
            
            # Start background tasks
            frame_task = asyncio.create_task(send_binary_frames(websocket, rpi_id))
            position_task = asyncio.create_task(send_position_updates(websocket, rpi_id))
            heartbeat_task = asyncio.create_task(send_heartbeats(websocket, rpi_id))
            message_task = asyncio.create_task(message_handler(websocket, rpi_id))
            
            # Wait for all tasks to complete
            await asyncio.gather(frame_task, position_task, heartbeat_task, message_task)
    
    except Exception as e:
        logger.error(f"Connection error: {e}")
    
    logger.info("Client shutting down")

async def main():
    """Main entry point with command line argument parsing."""
    global shutdown_requested
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Binary WebSocket Test Client")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="WebSocket server URL")
    parser.add_argument("--rpi-id", default=DEFAULT_RPI_ID, help="RPI ID to use")
    args = parser.parse_args()
    
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(globals(), 'shutdown_requested', True))
    
    try:
        logger.info("Starting Binary WebSocket Test Client")
        await run_binary_test_client(args.url, args.rpi_id)
    
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    
    finally:
        shutdown_requested = True
        logger.info("Test client shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())