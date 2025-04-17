#!/usr/bin/env python3
"""
Direct Command Xeryon Client
- No waiting for position
- Direct serial command transmission
- Maximum responsiveness with minimal latency
"""

import asyncio
import websockets
import json
import base64
import cv2
import time
import sys
import os
import random
import logging
from datetime import datetime
import threading
import signal

# Will be imported on the actual RPi
try:
    from picamera2 import Picamera2
    from websockets.exceptions import ConnectionClosed
    import serial
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
except ImportError:
    RUNNING_ON_RPI = False
    class ConnectionClosed(Exception):
        pass
    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1  # 100ms for more responsive position updates

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500

# Safety limits
MIN_POSITION = -30.0
MAX_POSITION = 30.0

# Global state
shutdown_requested = False
controller = None
axis = None
picam2 = None
position_lock = threading.Lock()
serial_lock = threading.Lock()
current_position = 0.0
startup_time = None

# Logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger("XeryonClient")

# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def initialize_xeryon_controller():
    """Initialize Xeryon controller with NO WAITING."""
    global controller, axis

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking Xeryon controller")
        return True

    try:
        logger.info(f"Initializing Xeryon controller on {COM_PORT}")
        
        # Create controller
        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        
        # Basic configuration (no waiting)
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.setSpeed(DEFAULT_SPEED)
        set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
        axis.sendCommand("ENBL=1")
        
        # No waiting for index - just send the command and continue
        axis.sendCommand("INDX=0")
        
        logger.info("Xeryon controller initialized")
        return True

    except Exception as e:
        logger.error(f"Xeryon controller initialization failed: {str(e)}")
        stop_controller()
        return False

def stop_controller():
    """Safely stop controller."""
    global controller, axis

    if not RUNNING_ON_RPI:
        return

    try:
        if controller:
            if axis:
                # Just send stop command
                axis.sendCommand("STOP=0")
            controller.stop()
    except Exception as e:
        logger.error(f"Error stopping controller: {str(e)}")
    finally:
        controller = None
        axis = None

def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration with NO WAITING."""
    if not RUNNING_ON_RPI or not axis:
        return False

    try:
        if acce_value is not None:
            acce_value = max(0, min(65500, int(acce_value)))
            axis.sendCommand(f"ACCE={acce_value}")

        if dece_value is not None:
            dece_value = max(0, min(65500, int(dece_value)))
            axis.sendCommand(f"DECE={dece_value}")

        axis.sendCommand("ENBL=1")
        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece: {str(e)}")
        return False

# ===== CAMERA MANAGEMENT =====
def initialize_camera():
    """Initialize camera with NO WAITING."""
    global picam2

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True

    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()

        # Basic configuration
        config = picam2.create_video_configuration(
            main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"}
        )

        picam2.configure(config)
        picam2.start()
        
        # Fixed settings
        picam2.set_controls({
            "AeEnable": False,
            "AfMode": 2,
            "ExposureTime": 20000,
            "AnalogueGain": 1.0
        })
        
        logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        return True

    except Exception as e:
        logger.error(f"Camera initialization failed: {str(e)}")
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
            if hasattr(picam2, 'close'):
                picam2.close()
    except Exception as e:
        logger.error(f"Error stopping camera: {str(e)}")
    finally:
        picam2 = None

async def encode_jpeg_async(frame, quality):
    """Encode a frame as JPEG asynchronously."""
    encode_param = [
        cv2.IMWRITE_JPEG_QUALITY, quality,
        cv2.IMWRITE_JPEG_OPTIMIZE, 1
    ]
    success, buffer = cv2.imencode('.jpg', frame, encode_param)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return buffer

# ===== COMMAND PROCESSING =====
async def process_command(data, websocket):
    """Process commands with NO WAITING for completion."""
    global axis, current_position

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))

    logger.debug(f"Command received: {command}, direction: {direction}, stepSize: {step_size}")

    response = {"status": "success", "rpiId": STATION_ID}

    try:
        # Handle ping/pong
        if message_type == "ping":
            response.update({
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            })
            await websocket.send(json.dumps(response))
            return
        elif message_type == "pong" or message_type == "heartbeat":
            return

        # Simulation mode
        if not RUNNING_ON_RPI or not axis:
            if RUNNING_ON_RPI:
                response["status"] = "error"
                response["message"] = "Controller not initialized"
            else:
                response["message"] = f"Simulation: {command}"
            await websocket.send(json.dumps(response))
            return

        # Handle acceleration and deceleration
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(direction) if direction.isdigit() else DEFAULT_ACCELERATION
            set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            await websocket.send(json.dumps(response))
            return

        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(direction) if direction.isdigit() else DEFAULT_DECELERATION
            set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            await websocket.send(json.dumps(response))
            return

        # Set both params if provided
        if acce_value is not None or dece_value is not None:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        # Process the main command - NO WAITING for completion
        if command in ["move", "step"]:
            if direction not in ["right", "left"]:
                raise ValueError(f"Invalid direction: {direction}")
            if step_size is None or not isinstance(step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "μm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")

            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
            final_step = step_value if direction == "right" else -step_value

            # Safety check - predict position
            predicted_position = current_position + final_step
            if predicted_position < MIN_POSITION or predicted_position > MAX_POSITION:
                response["status"] = "error"
                response["message"] = f"Movement exceeds safety limits ({MIN_POSITION} to {MAX_POSITION} mm)"
                await websocket.send(json.dumps(response))
                return

            # Just send the step command - don't wait
            axis.step(final_step)
            
            # Update position tracking
            with position_lock:
                current_position += final_step
                
            response["message"] = f"Moved {direction} by {step_size} {step_unit}"
            
        elif command == "stop":
            # Just send stop command
            axis.sendCommand("STOP=0")
            response["message"] = "Movement stopped"
            
        elif command == "home":
            # Just send DPOS=0 command
            axis.sendCommand("DPOS=0")
            with position_lock:
                current_position = 0
            response["message"] = "Homed to position 0"
            
        elif command == "scan":
            # Extract scan parameters
            scan_distance = float(data.get("scanDistance", 10))
            scan_cycles = int(data.get("scanCycles", 1))
            
            # Safety check
            scan_min = current_position - scan_distance/2
            scan_max = current_position + scan_distance/2
            
            if scan_min < MIN_POSITION or scan_max > MAX_POSITION:
                response["status"] = "error"
                response["message"] = f"Scan exceeds safety limits ({MIN_POSITION} to {MAX_POSITION} mm)"
                await websocket.send(json.dumps(response))
                return
            
            # Set scan parameters and start - no waiting
            axis.sendCommand(f"SCNL={scan_min}")
            axis.sendCommand(f"SCNH={scan_max}")
            axis.sendCommand(f"SCNN={scan_cycles}")
            axis.sendCommand("SCAN=1")
            
            response["message"] = f"Started scan from {scan_min} to {scan_max} mm"
            
        elif command == "reset":
            # Just restart controller
            stop_controller()
            initialize_xeryon_controller()
            response["message"] = "Controller reset"
            
        else:
            response["status"] = "error"
            response["message"] = f"Unknown command: {command}"

        # Send response
        await websocket.send(json.dumps(response))
            
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        response["status"] = "error"
        response["message"] = str(e)
        await websocket.send(json.dumps(response))

async def send_camera_frames(websocket):
    """Send camera frames with minimal processing."""
    frame_count = 0
    sleep_time = 1.0 / TARGET_FPS
    
    logger.info("Starting camera frame transmission")
    
    while not shutdown_requested and not websocket.closed:
        try:
            # Capture frame
            if RUNNING_ON_RPI and picam2:
                try:
                    frame = picam2.capture_array("main")
                    if frame is None:
                        await asyncio.sleep(sleep_time)
                        continue
                except Exception as e:
                    logger.error(f"Error capturing frame: {str(e)}")
                    await asyncio.sleep(sleep_time)
                    continue
            else:
                # Simple simulation frame
                frame_count += 1
                frame = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), dtype=np.uint8)
                frame[:, :] = (50, 50, 50)
                cv2.putText(frame, f"Frame: {frame_count}", (20, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            # Encode frame to JPEG
            buffer = await encode_jpeg_async(frame, JPEG_QUALITY)
            frame_data = base64.b64encode(buffer).decode('utf-8')
            
            # Send frame
            message = {
                "type": "camera_frame",
                "frame": f"data:image/jpeg;base64,{frame_data}",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Get position if available
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    message["epos"] = epos
                    
                    # Update position tracking
                    with position_lock:
                        current_position = epos
                except Exception:
                    pass
            
            await websocket.send(json.dumps(message))
            
            # Log occasional sends
            if frame_count % 100 == 0:
                logger.info(f"Sent frame #{frame_count}")
                
            # Sleep to maintain FPS
            await asyncio.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Error in frame sender: {str(e)}")
            await asyncio.sleep(sleep_time)
            
    logger.info("Frame sender stopped")

async def send_position_updates(websocket):
    """Send position updates directly from controller."""
    
    logger.info("Starting position updates")
    
    while not shutdown_requested and not websocket.closed:
        try:
            # Get position
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    
                    # Update position tracking
                    with position_lock:
                        current_position = epos
                except Exception as e:
                    await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                    continue
            else:
                # Simulation
                with position_lock:
                    epos = current_position
                    
            # Send position update
            if epos is not None:
                message = {
                    "type": "position_update",
                    "epos": epos,
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(message))
                
            # Sleep for update interval
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error in position updates: {str(e)}")
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
    logger.info("Position updates stopped")

async def health_checker(websocket):
    """Send periodic health updates and pings."""
    
    logger.info("Starting health checker")
    health_interval = 5.0  # 5 seconds
    
    while not shutdown_requested and not websocket.closed:
        try:
            # Send health update
            message = {
                "type": "health_update",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat(),
                "uptime": time.time() - startup_time if startup_time else 0,
                "status": "healthy"
            }
            await websocket.send(json.dumps(message))
            
            # Send ping for latency measurement
            ping_message = {
                "type": "ping",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(ping_message))
            
            # Sleep for health interval
            await asyncio.sleep(health_interval)
            
        except Exception as e:
            logger.error(f"Error in health checker: {str(e)}")
            await asyncio.sleep(health_interval)
            
    logger.info("Health checker stopped")

async def rpi_client():
    """Main client with minimal error handling."""
    global startup_time
    
    startup_time = time.time()
    logger.info(f"Starting Direct Command client for {STATION_ID}")
    
    # Signal handler for clean shutdown
    def handle_signal(sig, frame):
        global shutdown_requested
        logger.info(f"Received signal {sig}, shutting down")
        shutdown_requested = True
        
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Initialize hardware - no waiting for completion
    if RUNNING_ON_RPI:
        logger.info("Initializing hardware")
        initialize_xeryon_controller()
        initialize_camera()
    
    # Main connection loop
    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            
            # Connect to server
            websocket = await websockets.connect(SERVER_URL, ping_interval=None)
            logger.info("Connected to server")
            
            # Send registration
            register_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }
            await websocket.send(json.dumps(register_message))
            
            # Start background tasks
            camera_task = asyncio.create_task(send_camera_frames(websocket))
            position_task = asyncio.create_task(send_position_updates(websocket))
            health_task = asyncio.create_task(health_checker(websocket))
            
            # Main message loop
            while not shutdown_requested and not websocket.closed:
                try:
                    # Wait for messages
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    # Process command
                    await process_command(data, websocket)
                    
                except Exception as e:
                    logger.error(f"Error in message loop: {str(e)}")
                    if websocket.closed:
                        break
                        
            # Connection lost, clean up
            logger.warning("Connection closed, cleaning up")
            camera_task.cancel()
            position_task.cancel()
            health_task.cancel()
            
            # Wait briefly before reconnecting
            await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            await asyncio.sleep(1)
    
    # Shutdown
    await shutdown()
    
async def shutdown():
    """Clean shutdown."""
    logger.info("Shutting down")
    
    # Stop hardware
    if RUNNING_ON_RPI:
        stop_controller()
        stop_camera()
        
    logger.info("Shutdown complete")

async def main():
    """Entry point."""
    global startup_time
    
    startup_time = time.time()
    
    try:
        await rpi_client()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        # Import numpy if needed
        if not RUNNING_ON_RPI:
            import numpy as np
            
        # Run the client
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")