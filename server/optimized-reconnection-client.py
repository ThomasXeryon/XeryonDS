#!/usr/bin/env python3
"""
Ultra-Reliable Websocket Client for Xeryon Demo Station
- Maximum connection reliability with ultra-fast reconnections
- Aggressive reconnection with minimal delays
- Optimized for real-time performance with strict timeouts
- Prevents connection hanging with strict timeout enforcement
"""

import asyncio
import websockets
import json
import base64
import time
import signal
import sys
import os
import random
from datetime import datetime
import threading

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"

# Connection parameters - Ultra-fast reconnection settings
MAX_RECONNECT_ATTEMPTS = 9999  # Effectively infinite retries
RECONNECT_BASE_DELAY = 0.5     # Start with very short delay (500ms)
MAX_RECONNECT_DELAY = 5.0      # Cap at 5 seconds maximum
MAX_CONNECTION_TIMEOUT = 3.0   # Timeout for connection attempts
MAX_CLOSE_TIMEOUT = 1.0        # Timeout for connection closure
CONNECTION_HEARTBEAT_INTERVAL = 5.0  # Send heartbeats every 5 seconds

# Simulate position changes
SINE_WAVE_OSCILLATION = True   # Use sine wave for position simulation

# Global state
shutdown_requested = False
total_connection_failures = 0
reconnect_delay = RECONNECT_BASE_DELAY
frame_count = 0
current_position = 10.0  # Starting position

# ===== LOGGING SETUP =====
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("XeryonTestClient")

# ===== COMBINED CONNECTION CLIENT =====
async def rpi_combined_connection(rpi_id, url, max_attempts=MAX_RECONNECT_ATTEMPTS):
    """Establish a COMBINED connection for both camera and control"""
    global total_connection_failures, reconnect_delay, frame_count
    
    logger.info(f"Starting RPi client simulation for {rpi_id}")
    
    while total_connection_failures < max_attempts and not shutdown_requested:
        try:
            logger.info(f"Starting COMBINED connection to: {url} (attempt {total_connection_failures + 1}/{max_attempts})")
            
            # Connect with ultra-responsive optimized settings
            try:
                # Set super strict timeouts for fast connection detection
                websocket = await asyncio.wait_for(
                    websockets.connect(
                        url,
                        ping_interval=None,  # We'll implement our own application-level ping/pong
                        ping_timeout=None,   # Disable built-in ping timeouts entirely
                        close_timeout=MAX_CLOSE_TIMEOUT,  # Faster closing for quicker reconnection
                        max_size=10_000_000, # Allow large messages for camera frames
                        compression=None,    # Disable compression for speed
                    ), 
                    timeout=MAX_CONNECTION_TIMEOUT  # Strict timeout for connection attempt
                )
                logger.info("WebSocket connection established successfully")
            except asyncio.TimeoutError:
                logger.error(f"Connection timeout after {MAX_CONNECTION_TIMEOUT}s - will retry immediately")
                # Skip the backoff logic to retry immediately
                continue
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                # Will retry after handling backoff logic
                raise
                
            # Send registration message with combined type
            register_msg = {
                "type": "register",
                "rpiId": rpi_id, 
                "connectionType": "combined",
                "status": "ready",
                "message": f"RPi {rpi_id} combined connection initialized (Ultra-reliable v2.1)"
            }
            await websocket.send(json.dumps(register_msg))
            logger.info(f"Sent combined registration message")
            
            # Reset failure count on successful connection
            total_connection_failures = 0
            reconnect_delay = RECONNECT_BASE_DELAY
            
            # Start tasks for sending frames and handling commands
            frames_task = asyncio.create_task(send_frames(websocket, rpi_id))
            commands_task = asyncio.create_task(handle_commands(websocket, rpi_id))
            health_task = asyncio.create_task(send_health_updates(websocket, rpi_id))
            
            # Wait for any task to complete (which means it failed)
            done, pending = await asyncio.wait(
                [frames_task, commands_task, health_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel other tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
            # Log the task that completed
            for task in done:
                exception = task.exception()
                if exception:
                    logger.error(f"Task failed with error: {str(exception)}")
                else:
                    logger.info(f"Task completed normally")
                
            logger.warning("Connection or task failed - will reconnect")
            
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            
            # Ultra-fast reconnection with minimal delay
            total_connection_failures += 1
            
            # Use much more aggressive reconnection delay - optimized for ultra-reliability
            if "device not connected" in str(e).lower() or "cannot connect" in str(e).lower():
                # For connection refusals, retry almost immediately
                actual_delay = 0.1
                logger.warning(f"Connection refused - retrying almost immediately in {actual_delay:.1f}s")
            else:
                # For other errors, use a very short but slightly increasing delay
                # Cap at an extremely low value (MAX_RECONNECT_DELAY) for ultra-responsiveness 
                reconnect_delay = min(MAX_RECONNECT_DELAY, RECONNECT_BASE_DELAY * (1.2 ** min(total_connection_failures % 5, 4)))
                
                # Add minimal jitter to prevent reconnection storms (less than previous version)
                jitter = random.uniform(0, 0.1 * reconnect_delay)
                actual_delay = reconnect_delay + jitter
            
            logger.info(f"Retrying connection in {actual_delay:.2f}s (attempt {total_connection_failures})...")
            
            # For first few attempts, use even more aggressive retry
            if total_connection_failures < 3:
                actual_delay = min(0.1, actual_delay)  # Retry almost immediately for first 3 attempts
                logger.info(f"First few attempts - using ultra-fast retry ({actual_delay:.2f}s)")
                
            await asyncio.sleep(actual_delay)

    logger.error(f"Maximum connection attempts ({max_attempts}) reached. Giving up.")
    return None

async def send_frames(websocket, rpi_id):
    """Send simulated camera frames"""
    global frame_count, current_position
    
    import math
    
    while not shutdown_requested:
        try:
            # Simulate frames with position updates based on sine wave
            if SINE_WAVE_OSCILLATION:
                # Sine wave oscillation for interesting movement
                current_position = round(10.0 + 5.0 * math.sin(frame_count * 0.2), 3)
            else:
                # Random walk movement within bounds
                current_position += random.uniform(-0.2, 0.2)
                current_position = max(5.0, min(15.0, current_position))  # Keep within 5-15 range
                current_position = round(current_position, 3)  # Round to 3 decimal places
                
            # Create dummy frame data (base64 would normally be an image)
            frame_data = {
                "type": "camera_frame",
                "rpiId": rpi_id,
                "frameNumber": frame_count,
                "frame": "SGVsbG8gV29ybGQ="  # Base64 "Hello World" as test data
            }
            
            # Send frame with strict timeout
            await asyncio.wait_for(
                websocket.send(json.dumps(frame_data)),
                timeout=1.0  # 1 second timeout for sending frames
            )
            
            # Send position update with timestamp
            position_data = {
                "type": "position_update",
                "rpiId": rpi_id,
                "epos": current_position,
                "timestamp": datetime.now().isoformat()  # ISO format timestamp
            }
            
            # Send position with strict timeout
            await asyncio.wait_for(
                websocket.send(json.dumps(position_data)),
                timeout=1.0  # 1 second timeout for sending position
            )
            
            frame_count += 1
            logger.info(f"Sent frame #{frame_count} with position {current_position}")
            
            # Periodically send ping message
            if frame_count % 5 == 0:  # Every 5 frames
                ping_data = {
                    "type": "ping",
                    "timestamp": datetime.now().isoformat(),
                    "rpiId": rpi_id
                }
                logger.info(f"Sent ping message for latency measurement")
                await websocket.send(json.dumps(ping_data))
                
            # Wait before sending next frame
            await asyncio.sleep(1.1)  # Send a frame approximately every second
            
        except asyncio.TimeoutError:
            logger.error("Timeout sending frame - connection may be slow or dead")
            raise  # Reconnect by breaking task
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection closed while sending frames")
            raise  # Reconnect
        except Exception as e:
            logger.error(f"Error sending frames: {str(e)}")
            raise  # Reconnect

async def handle_commands(websocket, rpi_id):
    """Handle received command messages"""
    while not shutdown_requested:
        try:
            # Wait for a command with timeout
            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=5.0  # 5 second timeout for receiving commands
            )
            
            # Process the command
            data = json.loads(message)
            
            # Handle ping/pong messages
            if data.get("type") == "ping":
                # Reply with pong
                response = {
                    "type": "pong",
                    "timestamp": data.get("timestamp"),
                    "rpiId": rpi_id
                }
                await websocket.send(json.dumps(response))
                logger.info("Received ping message")
            elif data.get("type") == "pong":
                logger.info("Received pong response")
            elif data.get("type") == "command":
                # Process command
                command = data.get('command', 'unknown')
                direction = data.get('direction', 'none')
                stepSize = data.get('stepSize', 0)
                stepUnit = data.get('stepUnit', 'mm')
                acce = data.get('acce', None)  # Acceleration parameter
                dece = data.get('dece', None)  # Deceleration parameter
                
                # Handle both old and new command names
                display_command = command
                if command in ['acceleration', 'acce']:
                    display_command = 'acceleration'
                elif command in ['deceleration', 'dece']:
                    display_command = 'deceleration'
                
                # Create cleaner command display string
                cmd_display = f"{display_command}"
                if direction and direction != "none":
                    cmd_display += f" {direction}"
                if stepSize:
                    cmd_display += f" {stepSize}{stepUnit}"
                if acce is not None:
                    cmd_display += f" acce={acce}"
                if dece is not None:
                    cmd_display += f" dece={dece}"
                    
                logger.info(f"Received command: {cmd_display}")
                
                # Respond to commands with success message
                response = {
                    "type": "rpi_response",
                    "status": "success",
                    "rpiId": rpi_id,
                    "message": f"Command '{cmd_display}' executed successfully"
                }
                await websocket.send(json.dumps(response))
            else:
                logger.info(f"Received message: {data}")
                
        except asyncio.TimeoutError:
            # No command received within timeout, continue
            continue
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection closed while handling commands")
            raise  # Reconnect
        except Exception as e:
            logger.error(f"Error handling commands: {str(e)}")
            # Continue trying to receive commands unless connection is closed
            await asyncio.sleep(0.1)

async def send_health_updates(websocket, rpi_id):
    """Send periodic health status updates"""
    health_check_interval = CONNECTION_HEARTBEAT_INTERVAL
    uptime_start = time.time()
    
    while not shutdown_requested:
        try:
            # Calculate uptime
            uptime = time.time() - uptime_start
            
            # Create health data
            health_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": rpi_id,
                "uptime": uptime,
                "frame_count": frame_count,
                "position": current_position,
                "client_version": "2.1-ultra-reliable"
            }
            
            # Send health update with strict timeout
            try:
                await asyncio.wait_for(
                    websocket.send(json.dumps(health_data)),
                    timeout=2.0  # Strict timeout for health updates (2s max)
                )
            except asyncio.TimeoutError:
                logger.error("Health update send timed out - triggering reconnection")
                raise  # Exit to trigger reconnection
            
            # Wait for next health check interval
            await asyncio.sleep(health_check_interval)
            
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection closed while sending health updates")
            raise  # Reconnect
        except Exception as e:
            logger.error(f"Error sending health updates: {str(e)}")
            raise  # Reconnect

# Create a test frame image
def create_test_frame(frame_number, position):
    """Create a simulated test pattern as a base64 string"""
    try:
        # Create a simple test pattern
        import numpy as np
        import cv2
        
        # Create a blank image
        height, width = 480, 640
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Draw a grid pattern
        grid_size = 40
        for x in range(0, width, grid_size):
            cv2.line(img, (x, 0), (x, height), (50, 50, 50), 1)
        for y in range(0, height, grid_size):
            cv2.line(img, (0, y), (width, y), (50, 50, 50), 1)
            
        # Draw a marker showing the current position
        pos_x = int(width * (position - 5) / 10)  # Scale position 5-15 to screen width
        pos_x = max(0, min(width-1, pos_x))
        
        # Draw position marker
        cv2.circle(img, (pos_x, height//2), 10, (0, 0, 255), -1)
        cv2.line(img, (pos_x, height//2 - 20), (pos_x, height//2 + 20), (0, 255, 0), 2)
        
        # Add text
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, f"Frame: {frame_number}", (20, 30), font, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"Position: {position:.3f} mm", (20, 60), font, 0.7, (255, 255, 255), 2)
        cv2.putText(img, f"Time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}", (20, 90), font, 0.7, (255, 255, 255), 2)
        
        # Compress the image to JPEG
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
        # Convert to base64
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        
        return jpg_as_text
    except Exception as e:
        logger.error(f"Error creating test frame: {str(e)}")
        return "SGVsbG8gV29ybGQ="  # Return placeholder if error

async def run_demo(websocket, rpi_id):
    """Run a simulated demo sequence"""
    logger.info("Starting demo sequence")
    
    try:
        # Send a start message
        start_message = {
            "type": "rpi_response",
            "status": "info",
            "rpiId": rpi_id,
            "message": "Starting demo sequence"
        }
        await websocket.send(json.dumps(start_message))
        
        # Run a sequence of movements
        movements = [
            {"command": "move", "direction": "right", "stepSize": 5, "stepUnit": "mm"},
            {"command": "move", "direction": "left", "stepSize": 10, "stepUnit": "mm"},
            {"command": "move", "direction": "right", "stepSize": 8, "stepUnit": "mm"},
            {"command": "home"}
        ]
        
        for movement in movements:
            # Send command notification
            command_message = {
                "type": "rpi_response",
                "status": "info",
                "rpiId": rpi_id,
                "message": f"Demo executing: {movement['command']}"
            }
            await websocket.send(json.dumps(command_message))
            
            # Wait for simulated movement
            await asyncio.sleep(2)
            
        # Send completion message
        complete_message = {
            "type": "rpi_response",
            "status": "success",
            "rpiId": rpi_id,
            "message": "Demo sequence completed successfully"
        }
        await websocket.send(json.dumps(complete_message))
        
    except Exception as e:
        logger.error(f"Error in demo sequence: {str(e)}")
        try:
            error_message = {
                "type": "rpi_response",
                "status": "error",
                "rpiId": rpi_id,
                "message": f"Demo sequence failed: {str(e)}"
            }
            await websocket.send(json.dumps(error_message))
        except:
            pass

# Setup signal handlers for graceful shutdown
def setup_signal_handlers():
    global shutdown_requested
    
    def signal_handler(sig, frame):
        global shutdown_requested
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_requested = True
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point"""
    global shutdown_requested
    
    # Setup signal handlers
    setup_signal_handlers()
    
    # Get RPi ID from command line argument
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else 'RPI1'
    
    # Determine server URL
    server_url = None
    if len(sys.argv) > 2:
        server_url = sys.argv[2]
    else:
        # Try different URLs
        base_urls = [
            "ws://localhost:5000/rpi",                   # Local dev
            "wss://xeryonremotedemostation.replit.app/rpi"  # Production
        ]
        server_url = f"{base_urls[1]}/{rpi_id}"  # Default to production
    
    # Start the client
    logger.info(f"Starting ultra-reliable test client for {rpi_id}")
    logger.info(f"Connecting to {server_url}")
    
    try:
        await rpi_combined_connection(rpi_id, server_url)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        logger.info("Shutting down client")
        shutdown_requested = True

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")