#!/usr/bin/env python3
"""
Zero-Wait Raspberry Pi Client for Xeryon Demo Station
- Sends commands directly to USB without waiting for execution
- Eliminates all waiting and position verification
- Maximum real-time performance with no buffer issues
- Aggressive buffer management to prevent hanging
"""

import asyncio
import websockets
import json
import base64
from concurrent.futures import ThreadPoolExecutor
import cv2
import time
import sys
import os
import random
import logging
import gc
import subprocess
from datetime import datetime
from collections import deque
import threading
import signal

# Will be imported on the actual RPi
try:
    from picamera2 import Picamera2
    import serial
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
except ImportError:
    RUNNING_ON_RPI = False
    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.05  # 50ms position update interval

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.000001  # 1μs minimum sleep

# Connection parameters - Optimized for ultra-fast reconnection
MAX_RECONNECT_ATTEMPTS = 9999
RECONNECT_BASE_DELAY = 0.1
MAX_RECONNECT_DELAY = 3.0

# Buffer management
BUFFER_FLUSH_INTERVAL = 3.0  # Flush serial every 3 seconds
LAST_BUFFER_FLUSH = 0  # Last time buffer was flushed

# ===== GLOBAL STATE =====
shutdown_requested = False
controller = None
axis = None
picam2 = None
current_position = 0.0
startup_time = time.time()

# Locks
position_lock = threading.Lock()
serial_lock = threading.Lock()

# ===== LOGGING SETUP =====
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger("XeryonClient")


# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_buffer():
    """Flush serial buffer directly without any waits."""
    global LAST_BUFFER_FLUSH
    
    # Only flush every BUFFER_FLUSH_INTERVAL seconds
    current_time = time.time()
    if current_time - LAST_BUFFER_FLUSH < BUFFER_FLUSH_INTERVAL:
        return
    
    LAST_BUFFER_FLUSH = current_time
    
    if not RUNNING_ON_RPI or not controller:
        return

    try:
        if hasattr(controller, '_port'):
            controller._port.reset_input_buffer()
            controller._port.reset_output_buffer()
    except Exception as e:
        logger.error(f"Error flushing serial buffer: {e}")


def initialize_controller():
    """Initialize controller - no waiting."""
    global controller, axis
    
    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking controller")
        return True
        
    try:
        # Create controller
        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        
        # Send basic setup commands directly - NO WAITING
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.setSpeed(DEFAULT_SPEED)
        axis.sendCommand(f"ACCE={DEFAULT_ACCELERATION}")
        axis.sendCommand(f"DECE={DEFAULT_DECELERATION}")
        axis.sendCommand("ENBL=1")
        axis.sendCommand("INDX=0")  # No waiting for index
        
        logger.info("Controller initialized without waiting")
        return True
    except Exception as e:
        logger.error(f"Controller initialization error: {e}")
        return False


def stop_controller():
    """Stop controller."""
    global controller, axis
    
    if not RUNNING_ON_RPI:
        return
        
    try:
        if controller:
            if axis:
                axis.sendCommand("STOP=0")
            controller.stop()
    except Exception as e:
        logger.error(f"Error stopping controller: {e}")
    finally:
        controller = None
        axis = None


# ===== CAMERA MANAGEMENT =====
def initialize_camera():
    """Initialize camera with minimal setup."""
    global picam2
    
    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True
        
    try:
        picam2 = Picamera2()
        
        # Basic configuration
        config = picam2.create_video_configuration(
            main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"}
        )
        
        picam2.configure(config)
        picam2.start()
        
        # Basic camera settings
        picam2.set_controls({
            "AeEnable": False,
            "AfMode": 2,
            "ExposureTime": 20000,
            "AnalogueGain": 1.0
        })
        
        logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        return True
    except Exception as e:
        logger.error(f"Camera initialization error: {e}")
        return False


def stop_camera():
    """Stop camera."""
    global picam2
    
    if not RUNNING_ON_RPI:
        return
        
    try:
        if picam2:
            if hasattr(picam2, 'stop'):
                picam2.stop()
    except Exception as e:
        logger.error(f"Error stopping camera: {e}")
    finally:
        picam2 = None


# ===== COMMAND PROCESSING =====
def process_command_direct(data):
    """Process commands directly - NO WAITING, NO POSITION CHECKS."""
    global axis, current_position
    
    # Extract command information
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit", "mm")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))
    
    # For simulation mode or no controller
    if not RUNNING_ON_RPI or not axis:
        return {"status": "success", "message": f"Simulation: {command}", "rpiId": STATION_ID}
    
    # Periodically flush buffer
    with serial_lock:
        flush_serial_buffer()
    
    # Always send ENBL=1 before any command
    axis.sendCommand("ENBL=1")
    
    try:
        # Handle acceleration/deceleration
        if acce_value is not None:
            axis.sendCommand(f"ACCE={acce_value}")
            
        if dece_value is not None:
            axis.sendCommand(f"DECE={dece_value}")
            
        # Process main command
        if command in ["move", "step"] and step_size is not None:
            # Convert to mm
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1000000
                
            # Apply direction
            final_step = step_value if direction == "right" else -step_value
            
            # Send command directly without waiting
            axis.step(final_step)
            
            # Update position tracking (no waiting for actual position)
            with position_lock:
                current_position += final_step
                
            return {"status": "success", "message": f"Moved {direction}", "rpiId": STATION_ID}
            
        elif command == "home":
            # Just send findIndex command - don't wait
            axis.sendCommand("INDX=0")
            return {"status": "success", "message": "Homing", "rpiId": STATION_ID}
            
        elif command == "speed":
            # Set speed directly
            speed_value = float(direction) if direction.isdigit() else float(step_size) if step_size else DEFAULT_SPEED
            axis.setSpeed(speed_value)
            return {"status": "success", "message": f"Speed set to {speed_value}", "rpiId": STATION_ID}
            
        elif command == "scan":
            # Start scan - don't wait
            scan_direction = 1 if direction == "right" else -1
            axis.startScan(scan_direction)
            return {"status": "success", "message": f"Scanning {direction}", "rpiId": STATION_ID}
            
        elif command == "stop":
            # Send stop command - don't wait
            axis.sendCommand("STOP=0")
            return {"status": "success", "message": "Stopped", "rpiId": STATION_ID}
            
        elif command in ["acceleration", "acce"]:
            # Set acceleration - already done above
            return {"status": "success", "message": f"Acceleration set to {acce_value}", "rpiId": STATION_ID}
            
        elif command in ["deceleration", "dece"]:
            # Set deceleration - already done above
            return {"status": "success", "message": f"Deceleration set to {dece_value}", "rpiId": STATION_ID}
            
        elif command == "reset_params":
            # Reset parameters - don't wait
            axis.setSpeed(DEFAULT_SPEED)
            axis.sendCommand(f"ACCE={DEFAULT_ACCELERATION}")
            axis.sendCommand(f"DECE={DEFAULT_DECELERATION}")
            return {"status": "success", "message": "Parameters reset", "rpiId": STATION_ID}
            
        else:
            # Try to send as raw command
            axis.sendCommand(command)
            return {"status": "success", "message": f"Sent command: {command}", "rpiId": STATION_ID}
            
    except Exception as e:
        logger.error(f"Command error: {e}")
        try:
            # Try to recover
            axis.sendCommand("ENBL=1")
        except:
            pass
        return {"status": "error", "message": str(e), "rpiId": STATION_ID}


# ===== WEBSOCKET CLIENT =====
async def run_client():
    """Main WebSocket client with no blocking."""
    global shutdown_requested
    
    # Set up signal handler
    signal.signal(signal.SIGINT, lambda s, f: setattr(sys.modules[__name__], 'shutdown_requested', True))
    signal.signal(signal.SIGTERM, lambda s, f: setattr(sys.modules[__name__], 'shutdown_requested', True))
    
    # Initialize hardware without blocking
    if RUNNING_ON_RPI:
        initialize_controller()
        initialize_camera()
    
    # Connection loop
    reconnect_delay = RECONNECT_BASE_DELAY
    while not shutdown_requested:
        websocket = None
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            
            # Connect to server (no ping_interval)
            websocket = await websockets.connect(SERVER_URL, ping_interval=None, max_size=10_000_000)
            logger.info("Connected")
            
            # Register client
            await websocket.send(json.dumps({
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }))
            
            # Start background tasks
            frame_task = asyncio.create_task(send_frames(websocket))
            position_task = asyncio.create_task(send_positions(websocket))
            ping_task = asyncio.create_task(send_pings(websocket))
            
            # Main message handling loop
            while not shutdown_requested:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    # Handle ping separately
                    if data.get("type") == "ping":
                        await websocket.send(json.dumps({
                            "type": "pong",
                            "timestamp": data.get("timestamp"),
                            "rpiId": STATION_ID
                        }))
                        continue
                        
                    # Process command directly (no waiting)
                    response = process_command_direct(data)
                    
                    # Send response immediately
                    await websocket.send(json.dumps(response))
                    
                except Exception as e:
                    logger.error(f"Message handling error: {e}")
                    # Check if connection is still open
                    try:
                        await websocket.send(json.dumps({"type": "ping"}))
                    except:
                        logger.warning("Connection lost, reconnecting...")
                        break
            
            # Cancel background tasks
            frame_task.cancel()
            position_task.cancel()
            ping_task.cancel()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            
        finally:
            # Close websocket if open
            if websocket:
                try:
                    await websocket.close()
                except:
                    pass
                    
            # Wait before reconnecting
            await asyncio.sleep(reconnect_delay)
            # Increase reconnect delay with capping
            reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
    
    # Final cleanup
    if RUNNING_ON_RPI:
        stop_controller()
        stop_camera()
        

# ===== BACKGROUND TASKS =====
async def send_frames(websocket):
    """Send camera frames with no blocking."""
    global picam2
    
    frame_count = 0
    frame_interval = 1.0 / TARGET_FPS
    
    while not shutdown_requested:
        try:
            # Capture frame
            if RUNNING_ON_RPI and picam2:
                try:
                    frame = picam2.capture_array("main")
                    if frame is None:
                        await asyncio.sleep(frame_interval)
                        continue
                except Exception as e:
                    await asyncio.sleep(frame_interval)
                    continue
            else:
                # Create test frame
                frame_count += 1
                frame = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), dtype=np.uint8)
                frame[:, :] = (50, 50, 50)
                cv2.putText(frame, f"Frame: {frame_count}", (20, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            # Encode frame
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            frame_data = base64.b64encode(buffer).decode('utf-8')
            
            # Create message
            message = {
                "type": "camera_frame",
                "frame": f"data:image/jpeg;base64,{frame_data}",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Add position if available
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    message["epos"] = epos
                    
                    # Update position tracking
                    with position_lock:
                        current_position = epos
                except:
                    pass
                    
            # Send frame
            await websocket.send(json.dumps(message))
            
            # Sleep to maintain FPS
            await asyncio.sleep(frame_interval)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(frame_interval)


async def send_positions(websocket):
    """Send position updates."""
    global current_position
    
    while not shutdown_requested:
        try:
            # Get position
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    
                    # Update tracking
                    with position_lock:
                        current_position = epos
                        
                    # Send position update
                    message = {
                        "type": "position_update",
                        "epos": epos,
                        "rpiId": STATION_ID,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    await websocket.send(json.dumps(message))
                except:
                    pass
            else:
                # Send simulated position
                with position_lock:
                    epos = current_position
                    
                message = {
                    "type": "position_update",
                    "epos": epos,
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(message))
                
            # Sleep for update interval
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)


async def send_pings(websocket):
    """Send ping messages."""
    ping_interval = 5.0
    
    while not shutdown_requested:
        try:
            # Send ping
            message = {
                "type": "ping",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            await websocket.send(json.dumps(message))
            
            # Sleep for ping interval
            await asyncio.sleep(ping_interval)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(ping_interval)


# ===== MAIN ENTRY POINT =====
if __name__ == "__main__":
    try:
        # Import numpy if needed for simulation
        if not RUNNING_ON_RPI:
            import numpy as np
            
        # Run client
        asyncio.run(run_client())
    except KeyboardInterrupt:
        shutdown_requested = True
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Final cleanup
        if RUNNING_ON_RPI:
            stop_controller()
            stop_camera()