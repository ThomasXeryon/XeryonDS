#!/usr/bin/env python3
"""
Ultra Low Latency Client for Xeryon Demo Station
- Zero waiting: Commands sent directly
- No buffer issues: Aggressive buffer management
- Maximum real-time performance
- Compatible with older WebSocket libraries
"""

import asyncio
import websockets
import json
import base64
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
    import serial
    import cv2
    import numpy as np
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
except ImportError:
    RUNNING_ON_RPI = False
    import numpy as np
    import cv2
    logging.warning("Running in simulation mode")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1  # 100ms

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500

# Global state
shutdown_requested = False
controller = None
axis = None
picam2 = None
current_position = 0.0
websocket = None
connected = False
serial_lock = threading.Lock()
position_lock = threading.Lock()
last_flush_time = 0
FLUSH_INTERVAL = 3.0  # Flush serial port every 3 seconds

# Logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger("XeryonClient")

# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port(force=False):
    """Aggressively flush serial port to avoid buffer issues."""
    global last_flush_time
    
    current_time = time.time()
    if not force and (current_time - last_flush_time < FLUSH_INTERVAL):
        return True
        
    last_flush_time = current_time
    
    if not RUNNING_ON_RPI:
        return True

    try:
        if controller and hasattr(controller, '_port'):
            controller._port.reset_input_buffer()
            controller._port.reset_output_buffer()
            logger.debug("Serial buffers flushed")
        return True
    except Exception as e:
        logger.error(f"Error flushing serial port: {str(e)}")
        return False

def initialize_xeryon_controller():
    """Initialize Xeryon controller - no waiting."""
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
        
        # Basic configuration - no waiting
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.setSpeed(DEFAULT_SPEED)
        axis.sendCommand(f"ACCE={DEFAULT_ACCELERATION}")
        axis.sendCommand(f"DECE={DEFAULT_DECELERATION}")
        axis.sendCommand("ENBL=1")
        
        # Don't wait for find index - just send the command
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

# ===== CAMERA FUNCTIONS =====
def initialize_camera():
    """Initialize camera."""
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
    except Exception as e:
        logger.error(f"Error stopping camera: {str(e)}")
    finally:
        picam2 = None

# ===== COMMAND PROCESSING =====
async def process_command(data):
    """Just send commands directly - no waiting, no safety checks."""
    global axis, current_position, websocket

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))

    # Flush serial port periodically
    with serial_lock:
        flush_serial_port()

    # Create response
    response = {"status": "success", "rpiId": STATION_ID}

    # Handle ping/pong
    if message_type == "ping":
        response.update({
            "type": "pong",
            "timestamp": timestamp,
            "rpiId": STATION_ID
        })
        try:
            await websocket.send(json.dumps(response))
        except:
            pass
        return
    elif message_type == "pong" or message_type == "heartbeat":
        return

    # Handle simulation mode
    if not RUNNING_ON_RPI or not axis:
        response["message"] = f"Simulation: {command}"
        try:
            await websocket.send(json.dumps(response))
        except:
            pass
        return

    try:
        # Enable controller for any command
        axis.sendCommand("ENBL=1")
        
        # Process acceleration/deceleration
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(direction) if direction.isdigit() else DEFAULT_ACCELERATION
            axis.sendCommand(f"ACCE={acce_value}")
            response["message"] = f"Set acceleration to {acce_value}"
            
        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(direction) if direction.isdigit() else DEFAULT_DECELERATION
            axis.sendCommand(f"DECE={dece_value}")
            response["message"] = f"Set deceleration to {dece_value}"
            
        # Set parameters if provided with any command
        elif acce_value is not None:
            axis.sendCommand(f"ACCE={acce_value}")
        elif dece_value is not None:
            axis.sendCommand(f"DECE={dece_value}")
            
        # Process main commands - NO WAITING
        if command in ["move", "step"]:
            # Basic validation
            if step_size is None:
                step_size = 1.0  # Default
                
            # Convert to mm
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
                
            # Apply direction
            final_step = step_value if direction == "right" else -step_value
            
            # Just send step command - no waiting
            axis.step(final_step)
            
            # Update tracking
            with position_lock:
                current_position += final_step
                
            response["message"] = f"Moved {direction} by {step_size} {step_unit}"
            
        elif command == "stop":
            # Just send stop
            axis.sendCommand("STOP=0")
            response["message"] = "Stopped"
            
        elif command == "home":
            # Just set position to 0
            axis.sendCommand("DPOS=0")
            with position_lock:
                current_position = 0
            response["message"] = "Homed to position 0"
            
        elif command == "scan":
            # Extract parameters
            if step_size is not None:
                scan_distance = float(step_size)
            else:
                scan_distance = 10.0  # Default
                
            # Calculate scan range
            scan_min = current_position - scan_distance/2
            scan_max = current_position + scan_distance/2
            
            # Send scan commands directly
            axis.sendCommand(f"SCNL={scan_min}")
            axis.sendCommand(f"SCNH={scan_max}")
            axis.sendCommand(f"SCNN=1")  # Default 1 cycle
            axis.sendCommand("SCAN=1")
            
            response["message"] = f"Started scan {scan_distance}mm"
            
        elif command == "speed":
            # Set speed directly
            speed = int(direction) if direction.isdigit() else int(step_size) if step_size else DEFAULT_SPEED
            axis.setSpeed(speed)
            response["message"] = f"Set speed to {speed}"
            
        else:
            # Try to send as direct command
            axis.sendCommand(command)
            response["message"] = f"Sent command: {command}"

        # Send response
        try:
            await websocket.send(json.dumps(response))
        except:
            pass
            
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        response["status"] = "error"
        response["message"] = str(e)
        try:
            await websocket.send(json.dumps(response))
        except:
            pass

# ===== BACKGROUND TASKS =====
async def send_frames():
    """Send camera frames."""
    global websocket, connected
    
    frame_count = 0
    sleep_time = 1.0 / TARGET_FPS
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(0.5)
            continue
            
        try:
            # Capture frame
            if RUNNING_ON_RPI and picam2:
                try:
                    frame = picam2.capture_array("main")
                    if frame is None:
                        await asyncio.sleep(0.01)
                        continue
                except Exception as e:
                    await asyncio.sleep(0.01)
                    continue
            else:
                # Simple test frame
                frame_count += 1
                frame = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), dtype=np.uint8)
                frame[:, :] = (50, 50, 50)
                cv2.putText(frame, f"Frame: {frame_count}", (20, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            # Encode to JPEG
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            frame_data = base64.b64encode(buffer).decode('utf-8')
            
            # Get position directly - no waiting
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    with position_lock:
                        current_position = epos
                except:
                    pass
                    
            # Send frame with minimal processing
            message = {
                "type": "camera_frame",
                "frame": f"data:image/jpeg;base64,{frame_data}",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            if epos is not None:
                message["epos"] = epos
                
            try:
                await websocket.send(json.dumps(message))
            except Exception as e:
                await asyncio.sleep(0.01)
                continue
                
            # Sleep just enough to maintain FPS without overloading
            await asyncio.sleep(sleep_time)
                
        except Exception as e:
            await asyncio.sleep(0.01)

async def send_positions():
    """Send position updates."""
    global websocket, connected, current_position
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(0.5)
            continue
            
        try:
            # Get position directly - no waiting
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    with position_lock:
                        current_position = epos
                except:
                    await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                    continue
            else:
                with position_lock:
                    epos = current_position
                
            # Send position update
            message = {
                "type": "position_update",
                "epos": epos,
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                await websocket.send(json.dumps(message))
            except:
                await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                continue
                
            # Sleep for update interval
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except Exception:
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)

async def flush_buffers():
    """Flush buffers periodically."""
    global connected
    
    while not shutdown_requested:
        try:
            # Only flush when connected to avoid resource contention
            if connected and RUNNING_ON_RPI:
                with serial_lock:
                    flush_serial_port(force=True)
            
            # Sleep between flushes
            await asyncio.sleep(FLUSH_INTERVAL)
            
        except Exception:
            await asyncio.sleep(FLUSH_INTERVAL)

async def send_pings():
    """Send regular pings to keep connection alive."""
    global websocket, connected
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(2)
            continue
            
        try:
            # Send simple ping
            message = {
                "type": "ping",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                await websocket.send(json.dumps(message))
            except:
                await asyncio.sleep(5)
                continue
                
            # Sleep between pings
            await asyncio.sleep(5)
            
        except Exception:
            await asyncio.sleep(5)

# ===== MAIN CLIENT FUNCTION =====
async def run_client():
    """Main client function."""
    global websocket, connected, shutdown_requested
    
    # Set up signal handlers
    def handle_signal(sig, frame):
        global shutdown_requested
        logger.info(f"Received signal {sig}, shutting down")
        shutdown_requested = True
        
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Initialize hardware
    if RUNNING_ON_RPI:
        initialize_xeryon_controller()
        initialize_camera()
    
    # Start background tasks once
    frames_task = asyncio.create_task(send_frames())
    position_task = asyncio.create_task(send_positions())
    ping_task = asyncio.create_task(send_pings())
    flush_task = asyncio.create_task(flush_buffers())
    
    # Main connection loop
    reconnect_delay = 1.0
    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            
            # Connect with no ping/pong at protocol level
            websocket = await websockets.connect(SERVER_URL, ping_interval=None)
            logger.info("Connected")
            connected = True
            
            # Register with server
            register_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }
            await websocket.send(json.dumps(register_message))
            logger.info(f"Registered as {STATION_ID}")
            
            # Main message loop - just process incoming commands
            while not shutdown_requested:
                try:
                    # Get and process messages
                    message = await websocket.recv()
                    data = json.loads(message)
                    asyncio.create_task(process_command(data))
                except Exception as e:
                    logger.error(f"Error in message loop: {str(e)}")
                    # Test if connection still good
                    try:
                        await websocket.send(json.dumps({"type": "ping"}))
                    except:
                        logger.warning("Connection appears closed")
                        break
        
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            connected = False
            
            # Exponential backoff with jitter for reconnection
            jitter = random.uniform(0.8, 1.2)
            sleep_time = min(reconnect_delay * jitter, 10.0)
            logger.info(f"Reconnecting in {sleep_time:.1f}s")
            await asyncio.sleep(sleep_time)
            
            # Increase backoff delay, but reset if it gets too long
            reconnect_delay = min(reconnect_delay * 1.5, 5.0)
            
        finally:
            # Always mark as disconnected
            connected = False
            # Clean up the connection
            try:
                await websocket.close()
            except:
                pass
    
    # Cleanup when shutting down
    for task in [frames_task, position_task, ping_task, flush_task]:
        task.cancel()
        
    # Stop hardware
    if RUNNING_ON_RPI:
        stop_controller()
        stop_camera()
    
    logger.info("Client shutdown complete")

if __name__ == "__main__":
    try:
        # Run the client
        asyncio.run(run_client())
    except KeyboardInterrupt:
        shutdown_requested = True
        logger.info("Keyboard interrupt received, exiting")