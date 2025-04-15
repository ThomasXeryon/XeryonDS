#!/usr/bin/env python3
"""
Bulletproof Test Client Simulator for Xeryon Remote Demo Station
- Simulates the RPi client behavior in a test environment
- Ultra-reliable with real-time performance
- Includes error simulation for testing robustness
"""

import asyncio
import websockets
import json
import base64
import time
import sys
import random
import logging
import io
import os
import cv2
import numpy as np
from datetime import datetime
from collections import deque

# ===== CONFIGURATION =====
DEFAULT_RPI_ID = "RPI1"
DEFAULT_SERVER_URL = "ws://localhost:5000/rpi/{rpi_id}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
FRAME_RATE = 30  # frames per second
JPEG_QUALITY = 70
MAX_RECONNECT_ATTEMPTS = 20

# ===== LOGGING SETUP =====
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestClient")

# ===== GLOBAL STATE =====
shutdown_requested = False
position = 0.0  # Current simulated position
position_direction = 1  # Direction of movement (1 = positive, -1 = negative)
scan_active = False  # Is a scan operation active?
scan_speed = 0.5  # mm per update during scan
step_size = 0.0  # For tracking last step
demo_running = False
frame_count = 0
startup_time = time.time()

# ===== POSITION DATA GENERATION =====
def update_position(command=None, direction=None, step_size_mm=None):
    """Update the simulated position based on commands or scanning."""
    global position, position_direction, scan_active, step_size
    
    # Position limits
    MIN_POSITION = -30.0
    MAX_POSITION = 30.0
    
    # Handle specific commands
    if command == "home":
        position = 0.0
        scan_active = False
        return position
        
    elif command == "stop":
        position = 0.0
        scan_active = False
        return position
        
    elif command == "step" or command == "move":
        if direction and step_size_mm:
            dir_multiplier = 1 if direction == "right" else -1
            step_size = step_size_mm
            new_position = position + (step_size * dir_multiplier)
            
            # Constrain to limits
            position = max(MIN_POSITION, min(MAX_POSITION, new_position))
            scan_active = False
            return position
            
    elif command == "scan":
        if direction:
            scan_active = True
            position_direction = 1 if direction == "right" else -1
            return position
            
    elif command == "stop_scan":
        scan_active = False
        return position
        
    # Update position for continuous scan
    if scan_active:
        # Update position in the direction of scan
        new_position = position + (scan_speed * position_direction)
        
        # Check if we've hit a limit
        if new_position >= MAX_POSITION:
            position = MAX_POSITION
            position_direction = -1  # Bounce off the limit
        elif new_position <= MIN_POSITION:
            position = MIN_POSITION
            position_direction = 1  # Bounce off the limit
        else:
            position = new_position
            
    return position

def create_test_frame(frame_number, position):
    """Create a test image with frame number, position and current time."""
    # Create a blank image
    image = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), dtype=np.uint8)
    
    # Fill with a gradient background
    for y in range(RESOLUTION_HEIGHT):
        for x in range(RESOLUTION_WIDTH):
            image[y, x] = [
                int(255 * (1 - y / RESOLUTION_HEIGHT)),  # Blue
                int(255 * (x / RESOLUTION_WIDTH)),       # Green
                int(255 * (position + 30) / 60)          # Red (based on position)
            ]
    
    # Calculate a position indicator
    pos_x = int((position + 30) / 60 * RESOLUTION_WIDTH)
    cv2.line(image, (pos_x, 0), (pos_x, RESOLUTION_HEIGHT), (255, 255, 255), 3)
    
    # Add text overlay
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    cv2.putText(image, f"Frame: {frame_number}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(image, f"Position: {position:.3f} mm", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(image, f"Time: {timestamp}", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    # Encode as JPEG
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    _, buffer = cv2.imencode('.jpg', image, encode_param)
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    
    return jpg_as_text

# ===== WEBSOCKET HANDLER =====
async def handle_messages(websocket, rpi_id):
    """Process incoming messages and send appropriate responses."""
    global position, scan_active, demo_running
    
    while not shutdown_requested:
        try:
            message = await websocket.recv()
            try:
                data = json.loads(message)
                message_type = data.get("type")
                command = data.get("command", "")
                
                # Handle different message types
                if message_type == "ping":
                    # Respond to ping for latency measurement
                    response = {
                        "type": "pong",
                        "timestamp": data.get("timestamp"),
                        "rpiId": rpi_id
                    }
                    await websocket.send(json.dumps(response))
                    logger.debug(f"Replied to ping: {data.get('timestamp')}")
                    
                elif message_type == "command":
                    # Process the command
                    direction = data.get("direction")
                    step_size_raw = data.get("stepSize")
                    step_unit = data.get("stepUnit", "mm")
                    
                    # Convert step size to mm if needed
                    step_size_mm = None
                    if step_size_raw is not None:
                        step_size_mm = float(step_size_raw)
                        if step_unit == "μm":
                            step_size_mm /= 1000
                        elif step_unit == "nm":
                            step_size_mm /= 1000000
                    
                    # Update the position based on the command
                    new_position = update_position(command, direction, step_size_mm)
                    
                    # Send response back to server
                    response = {
                        "status": "success",
                        "rpiId": rpi_id,
                        "message": f"Executed {command}"
                    }
                    
                    # Add command-specific data
                    if command in ["move", "step"]:
                        dir_multiplier = 1 if direction == "right" else -1
                        step_mm = step_size_mm * dir_multiplier
                        response["message"] = f"Stepped {step_mm:.6f} mm {direction}"
                        response["step_executed_mm"] = step_mm
                    elif command == "home":
                        response["message"] = "Homed to index (0 mm)"
                    elif command == "scan":
                        response["message"] = f"Scanning {direction}"
                    elif command == "stop":
                        response["message"] = "Stopped, position reset to 0 mm"
                    elif command == "demo_start":
                        demo_running = True
                        response["message"] = "Demo started"
                    elif command == "demo_stop":
                        demo_running = False
                        response["message"] = "Demo stopped"
                        
                    # Send the response
                    await websocket.send(json.dumps(response))
                    logger.info(f"Executed command: {command}, new position: {new_position:.3f} mm")
                    
                    # If it's a demo command, start a background task
                    if command == "demo_start" and demo_running:
                        asyncio.create_task(run_demo(websocket, rpi_id))
                
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
            
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed by server")
            break
        except Exception as e:
            logger.error(f"Message handler error: {str(e)}")
            await asyncio.sleep(0.1)
            
        # Small delay to prevent CPU hogging
        await asyncio.sleep(0.01)

async def send_frames(websocket, rpi_id):
    """Send simulated camera frames."""
    global frame_count
    
    logger.info("Starting frame sender task")
    
    # Timing control
    frame_interval = 1.0 / FRAME_RATE
    last_frame_time = time.time()
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            elapsed = current_time - last_frame_time
            
            # Sleep to maintain frame rate
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
                
            last_frame_time = time.time()
            
            # Create and send a test frame
            jpg_data = create_test_frame(frame_count, position)
            
            frame_data = {
                "type": "camera_frame",
                "rpiId": rpi_id,
                "frame": jpg_data,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            await websocket.send(json.dumps(frame_data))
            
            if frame_count % 20 == 0:
                logger.debug(f"Sent frame #{frame_count} with position {position:.3f}")
                
            frame_count += 1
            
        except Exception as e:
            logger.error(f"Frame sender error: {str(e)}")
            await asyncio.sleep(0.1)
            
        # Small delay to prevent CPU hogging
        await asyncio.sleep(0.01)

async def send_position_updates(websocket, rpi_id):
    """Send regular position updates."""
    update_interval = 0.05  # 50ms
    last_update_time = time.time()
    last_sent_position = None
    
    logger.info("Starting position update sender task")
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            elapsed = current_time - last_update_time
            
            # Update at a fixed interval
            if elapsed >= update_interval:
                last_update_time = current_time
                
                # Only send if position changed or every second
                if position != last_sent_position or elapsed > 1.0:
                    position_data = {
                        "type": "position_update",
                        "rpiId": rpi_id,
                        "epos": position,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    await websocket.send(json.dumps(position_data))
                    last_sent_position = position
                    
                    # Log occasionally
                    if int(position * 100) % 50 == 0:  # Log at 0.5mm intervals
                        logger.debug(f"Position update: {position:.3f} mm")
            
            # If scanning is active, continuously update position
            if scan_active:
                update_position()
                
            # Sleep to maintain update rate
            await asyncio.sleep(update_interval)
            
        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            await asyncio.sleep(0.1)

async def send_health_updates(websocket, rpi_id):
    """Send periodic health status updates."""
    health_interval = 5.0  # seconds
    
    logger.info("Starting health update sender task")
    
    while not shutdown_requested:
        try:
            # Create health data
            uptime = time.time() - startup_time
            health_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": rpi_id,
                "uptime": uptime,
                "status": "healthy",
                "cpu_usage": random.uniform(10, 30),  # Simulated values
                "memory_usage": random.uniform(20, 40)
            }
            
            await websocket.send(json.dumps(health_data))
            
            # Wait for next update
            await asyncio.sleep(health_interval)
            
        except Exception as e:
            logger.error(f"Health update error: {str(e)}")
            await asyncio.sleep(1)

async def run_demo(websocket, rpi_id):
    """Run a simulated demo sequence."""
    global position, scan_active, demo_running
    
    logger.info("Demo sequence started")
    
    try:
        # Reset position
        position = 0.0
        scan_active = False
        
        # Run demo sequence
        while demo_running and not shutdown_requested:
            # Choose a random action
            action = random.choice(["step", "scan"])
            
            if action == "step":
                # Random step
                step_size = random.uniform(0.5, 3.0)
                direction = random.choice(["right", "left"])
                
                # Calculate new position
                dir_multiplier = 1 if direction == "right" else -1
                new_position = position + (step_size * dir_multiplier)
                
                # Ensure within bounds
                if -30 <= new_position <= 30:
                    position = new_position
                    logger.info(f"Demo: Step {step_size:.2f} mm {direction}")
                    
                # Wait briefly
                await asyncio.sleep(random.uniform(0.3, 1.0))
                
            else:  # scan
                # Start scanning in random direction
                scan_active = True
                position_direction = random.choice([1, -1])
                direction_name = "right" if position_direction == 1 else "left"
                logger.info(f"Demo: Scan {direction_name}")
                
                # Scan for a random duration
                scan_duration = random.uniform(1.0, 3.0)
                await asyncio.sleep(scan_duration)
                
                # Stop scanning
                scan_active = False
                logger.info("Demo: Scan stopped")
                
                # Pause briefly
                await asyncio.sleep(random.uniform(0.2, 0.8))
                
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        # Clean up
        demo_running = False
        scan_active = False
        logger.info("Demo sequence ended")

async def handle_client_connection(rpi_id, url):
    """Establish and maintain a connection to the server."""
    global shutdown_requested, total_connection_failures
    
    connection_attempts = 0
    reconnect_delay = 1.0
    
    logger.info(f"Starting combined RPi client for {rpi_id}")
    logger.info(f"Connecting to: {url}")
    
    while not shutdown_requested and connection_attempts < MAX_RECONNECT_ATTEMPTS:
        try:
            connection_attempts += 1
            logger.info(f"Starting connection to: {url} (attempt {connection_attempts}/{MAX_RECONNECT_ATTEMPTS})")
            
            # Connect to server
            async with websockets.connect(url) as websocket:
                # Send registration message
                registration = {
                    "type": "register",
                    "rpiId": rpi_id,
                    "connectionType": "combined",
                    "status": "ready",
                    "message": f"Bulletproof Test Client for {rpi_id} initialized",
                    "connectionId": f"test_{int(time.time())}",
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(registration))
                logger.info(f"Sent combined registration message")
                
                # Start background tasks
                message_handler = asyncio.create_task(handle_messages(websocket, rpi_id))
                frame_sender = asyncio.create_task(send_frames(websocket, rpi_id))
                position_sender = asyncio.create_task(send_position_updates(websocket, rpi_id))
                health_sender = asyncio.create_task(send_health_updates(websocket, rpi_id))
                
                # Reset reconnection delay on successful connection
                connection_attempts = 0
                reconnect_delay = 1.0
                
                # Wait for any task to complete (which indicates an error or disconnect)
                done, pending = await asyncio.wait(
                    [message_handler, frame_sender, position_sender, health_sender],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    
                # Check what happened
                for task in done:
                    try:
                        task.result()
                    except Exception as e:
                        logger.error(f"Task error: {str(e)}")
                        
                logger.warning("Connection or task error - will reconnect")
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            
            # Use exponential backoff for reconnection
            reconnect_delay = min(30, reconnect_delay * 1.5)
            jitter = random.uniform(0, 0.3 * reconnect_delay)
            actual_delay = reconnect_delay + jitter
            
            logger.info(f"Reconnecting in {actual_delay:.1f} seconds...")
            await asyncio.sleep(actual_delay)
            
    if connection_attempts >= MAX_RECONNECT_ATTEMPTS:
        logger.error(f"Maximum connection attempts ({MAX_RECONNECT_ATTEMPTS}) reached - giving up")

# ===== MAIN FUNCTION =====
async def main():
    """Main entry point with argument parsing."""
    global shutdown_requested
    
    # Parse command-line arguments
    rpi_id = DEFAULT_RPI_ID
    server_url = None
    
    if len(sys.argv) > 1:
        rpi_id = sys.argv[1]
        
    if len(sys.argv) > 2:
        server_url = sys.argv[2]
    else:
        server_url = DEFAULT_SERVER_URL.format(rpi_id=rpi_id)
        
    # Print startup banner
    logger.info("=" * 60)
    logger.info(f"Starting Bulletproof Test Client for {rpi_id}")
    logger.info(f"Connecting to {server_url}")
    logger.info("=" * 60)
    
    try:
        # Set up handling for graceful shutdown
        loop = asyncio.get_running_loop()
        for signal_name in ('SIGINT', 'SIGTERM'):
            try:
                loop.add_signal_handler(
                    getattr(signal, signal_name),
                    lambda: asyncio.create_task(shutdown())
                )
            except (NotImplementedError, AttributeError):
                # Windows doesn't support SIGTERM
                pass
                
        # Start the client connection
        await handle_client_connection(rpi_id, server_url)
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        await shutdown()

async def shutdown():
    """Perform a clean shutdown."""
    global shutdown_requested
    
    if shutdown_requested:
        return
        
    shutdown_requested = True
    logger.info("Shutting down...")
    
    # Give tasks time to terminate gracefully
    await asyncio.sleep(1)
    
    logger.info("Shutdown complete")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    try:
        import signal
        asyncio.run(main())
    except KeyboardInterrupt:
        pass