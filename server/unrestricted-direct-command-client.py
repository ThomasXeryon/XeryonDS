#!/usr/bin/env python3
"""
Unrestricted Direct Command Client for Xeryon Demo Station
- Full functionality with no safety limits
- Immediate command execution
- Zero waiting for position
- Passes all commands directly to controller without restrictions
- Compatible with older websockets libraries
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
    from websockets.exceptions import ConnectionClosed
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
    class ConnectionClosed(Exception):
        pass
    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = "wss://xeryonremotedemostation.replit.app/rpi/RPI1"
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
position_lock = threading.Lock()
serial_lock = threading.Lock()
current_position = 0.0
startup_time = None
websocket = None  # Global websocket object
last_scan_min = -30.0
last_scan_max = 30.0
last_scan_cycles = 1

# Logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger("XeryonClient")

# ===== XERYON CONTROLLER FUNCTIONS =====
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
        
        # Basic configuration - no waiting
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.setSpeed(DEFAULT_SPEED)
        set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
        axis.sendCommand("ENBL=1")
        
        # No waiting for index - just send the command
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
            # No min/max limits - just send the value
            axis.sendCommand(f"ACCE={acce_value}")

        if dece_value is not None:
            # No min/max limits - just send the value
            axis.sendCommand(f"DECE={dece_value}")

        axis.sendCommand("ENBL=1")
        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece: {str(e)}")
        return False

def send_raw_command(command):
    """Send a raw command string directly to the controller."""
    if not RUNNING_ON_RPI or not axis:
        return False
        
    try:
        axis.sendCommand(command)
        return True
    except Exception as e:
        logger.error(f"Error sending raw command '{command}': {str(e)}")
        return False

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
async def process_command(data):
    """Process commands with NO WAITING for completion and NO SAFETY LIMITS."""
    global axis, current_position, websocket
    global last_scan_min, last_scan_max, last_scan_cycles

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))
    raw_command = data.get("rawCommand")

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

        # Handle raw command if present
        if raw_command:
            send_raw_command(raw_command)
            response["message"] = f"Sent raw command: {raw_command}"
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

        # Set acce/dece params if provided
        if acce_value is not None or dece_value is not None:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        # Process the main command - NO WAITING for completion, NO SAFETY LIMITS
        if command in ["move", "step"]:
            if step_size is None:
                step_size = 1.0  # Default step size
                
            if step_unit is None:
                step_unit = "mm"  # Default unit
                
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
                
            # Determine direction
            final_step = step_value if direction == "right" else -step_value
            
            # Just send the step command - no waiting, no position checking
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
            
            # Calculate scan range based on current position
            scan_min = current_position - scan_distance/2
            scan_max = current_position + scan_distance/2
            
            # Store for future reference
            last_scan_min = scan_min
            last_scan_max = scan_max
            last_scan_cycles = scan_cycles
            
            # Set scan parameters and start - no waiting, no position checking
            axis.sendCommand(f"SCNL={scan_min}")
            axis.sendCommand(f"SCNH={scan_max}")
            axis.sendCommand(f"SCNN={scan_cycles}")
            axis.sendCommand("SCAN=1")
            
            response["message"] = f"Started scan from {scan_min} to {scan_max} mm for {scan_cycles} cycles"
            
        elif command == "reset":
            # Just restart controller
            stop_controller()
            initialize_xeryon_controller()
            response["message"] = "Controller reset"
            
        elif command == "enable":
            # Enable axis
            axis.sendCommand("ENBL=1")
            response["message"] = "Axis enabled"
            
        elif command == "disable":
            # Disable axis
            axis.sendCommand("ENBL=0")
            response["message"] = "Axis disabled"
            
        elif command == "set_position":
            # Set absolute position
            if step_size is not None:
                position = float(step_size)
                if step_unit == "μm":
                    position /= 1000
                elif step_unit == "nm":
                    position /= 1_000_000
                    
                # Set position directly with no checks
                axis.sendCommand(f"DPOS={position}")
                with position_lock:
                    current_position = position
                response["message"] = f"Set position to {position} mm"
            else:
                response["status"] = "error"
                response["message"] = "No position specified"
                
        elif command == "repeat_scan":
            # Repeat last scan
            if last_scan_min is not None and last_scan_max is not None:
                axis.sendCommand(f"SCNL={last_scan_min}")
                axis.sendCommand(f"SCNH={last_scan_max}")
                axis.sendCommand(f"SCNN={last_scan_cycles}")
                axis.sendCommand("SCAN=1")
                response["message"] = f"Repeating scan from {last_scan_min} to {last_scan_max} mm for {last_scan_cycles} cycles"
            else:
                response["status"] = "error"
                response["message"] = "No previous scan to repeat"
            
        elif command == "set_speed":
            # Set speed
            if step_size is not None:
                speed = int(step_size)
                axis.setSpeed(speed)
                response["message"] = f"Set speed to {speed}"
            else:
                response["status"] = "error"
                response["message"] = "No speed specified"
                
        elif command == "get_data":
            # Get data from controller
            if direction:
                data_value = axis.getData(direction)
                response["value"] = data_value
                response["message"] = f"Got {direction}={data_value}"
            else:
                response["status"] = "error"
                response["message"] = "No data parameter specified"
                
        else:
            # Try to send as raw command
            success = send_raw_command(command)
            if success:
                response["message"] = f"Sent raw command: {command}"
            else:
                response["status"] = "error"
                response["message"] = f"Unknown command: {command}"

        # Send response
        await websocket.send(json.dumps(response))
            
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        response["status"] = "error"
        response["message"] = str(e)
        try:
            await websocket.send(json.dumps(response))
        except:
            pass

# ===== BACKGROUND TASKS =====
async def camera_frame_sender():
    """Send camera frames."""
    global websocket
    
    frame_count = 0
    sleep_time = 1.0 / TARGET_FPS
    
    logger.info("Starting camera frame transmission")
    
    while not shutdown_requested:
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
            
            # Create message
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
            
            # Check if connection is still active before sending
            try:
                await websocket.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending frame: {str(e)}")
                await asyncio.sleep(sleep_time)
                continue
                
            # Log occasional sends
            if frame_count % 100 == 0:
                logger.info(f"Sent frame #{frame_count}")
                
            # Sleep to maintain FPS
            await asyncio.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Error in camera frame loop: {str(e)}")
            await asyncio.sleep(sleep_time)
            
    logger.info("Frame sender stopped")

async def position_updater():
    """Send position updates."""
    global websocket
    
    logger.info("Starting position updates")
    
    while not shutdown_requested:
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
                    
            # Create message
            message = {
                "type": "position_update",
                "epos": epos,
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            # Check if connection is still active before sending
            try:
                await websocket.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending position: {str(e)}")
                await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                continue
                
            # Sleep for update interval
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error in position updates: {str(e)}")
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
    logger.info("Position updates stopped")

async def health_checker():
    """Send periodic health updates and pings."""
    global websocket
    
    logger.info("Starting health checker")
    health_interval = 5.0  # 5 seconds
    
    while not shutdown_requested:
        try:
            # Get controller status if available
            status = "healthy"
            if RUNNING_ON_RPI and axis:
                try:
                    stat = axis.getData("STAT")
                    # Include status flags
                    message_status = {
                        "type": "health_update",
                        "rpiId": STATION_ID,
                        "timestamp": datetime.now().isoformat(),
                        "uptime": time.time() - startup_time if startup_time else 0,
                        "status": status,
                        "controller_status": stat
                    }
                    
                    # Send detailed status
                    try:
                        await websocket.send(json.dumps(message_status))
                    except Exception as e:
                        logger.error(f"Error sending health update: {str(e)}")
                        await asyncio.sleep(health_interval)
                        continue
                except Exception:
                    # Send basic status if couldn't get STAT
                    message = {
                        "type": "health_update",
                        "rpiId": STATION_ID,
                        "timestamp": datetime.now().isoformat(),
                        "uptime": time.time() - startup_time if startup_time else 0,
                        "status": status
                    }
                    
                    try:
                        await websocket.send(json.dumps(message))
                    except Exception as e:
                        logger.error(f"Error sending health update: {str(e)}")
                        await asyncio.sleep(health_interval)
                        continue
            else:
                # Send basic status
                message = {
                    "type": "health_update",
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat(),
                    "uptime": time.time() - startup_time if startup_time else 0,
                    "status": status
                }
                
                try:
                    await websocket.send(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error sending health update: {str(e)}")
                    await asyncio.sleep(health_interval)
                    continue
                
            # Send ping for latency measurement
            ping_message = {
                "type": "ping",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                await websocket.send(json.dumps(ping_message))
            except Exception as e:
                logger.error(f"Error sending ping: {str(e)}")
                await asyncio.sleep(health_interval)
                continue
                
            # Sleep for health interval
            await asyncio.sleep(health_interval)
            
        except Exception as e:
            logger.error(f"Error in health checker: {str(e)}")
            await asyncio.sleep(health_interval)
            
    logger.info("Health checker stopped")

# ===== BUFFER MANAGEMENT =====
async def flush_buffers():
    """Periodically flush USB buffers to prevent hanging."""
    if not RUNNING_ON_RPI:
        return
        
    flush_interval = 15.0  # Flush every 15 seconds
    
    logger.info("Starting buffer flushing task")
    
    while not shutdown_requested:
        try:
            logger.debug("Flushing serial port buffers")
            if controller and axis:
                try:
                    # Try to flush serial port directly
                    if hasattr(controller, '_port'):
                        controller._port.reset_input_buffer()
                        controller._port.reset_output_buffer()
                except Exception as e:
                    logger.error(f"Error flushing buffers: {str(e)}")
                    
            # Wait for next flush
            await asyncio.sleep(flush_interval)
        except Exception as e:
            logger.error(f"Error in buffer flushing: {str(e)}")
            await asyncio.sleep(flush_interval)
            
    logger.info("Buffer flushing task stopped")

# ===== MAIN CLIENT FUNCTION =====
async def main():
    """Main client function."""
    global shutdown_requested, startup_time, websocket
    
    startup_time = time.time()
    logger.info(f"Starting unrestricted direct command client for {STATION_ID}")
    
    # Set up signal handlers
    def handle_signal(sig, frame):
        global shutdown_requested
        logger.info(f"Received signal {sig}, shutting down")
        shutdown_requested = True
        
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Initialize hardware
    if RUNNING_ON_RPI:
        logger.info("Initializing hardware")
        init_ok = initialize_xeryon_controller()
        if init_ok:
            logger.info("Controller initialized successfully")
        else:
            logger.warning("Controller initialization failed, continuing anyway")
            
        cam_ok = initialize_camera()
        if cam_ok:
            logger.info("Camera initialized successfully")
        else:
            logger.warning("Camera initialization failed, continuing anyway")
    
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
            logger.info(f"Registered as {STATION_ID} with combined connection")
            
            # Start background tasks
            camera_task = asyncio.create_task(camera_frame_sender())
            position_task = asyncio.create_task(position_updater())
            health_task = asyncio.create_task(health_checker())
            flush_task = asyncio.create_task(flush_buffers())
            
            # Main message loop - receive and process messages
            while not shutdown_requested:
                try:
                    # Wait for message
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    # Process message
                    await process_command(data)
                    
                except Exception as e:
                    logger.error(f"Error in message loop: {str(e)}")
                    # Check if the connection is still open
                    try:
                        # Send a ping to test connection
                        ping_test = {
                            "type": "ping",
                            "timestamp": datetime.now().isoformat(),
                            "rpiId": STATION_ID
                        }
                        await websocket.send(json.dumps(ping_test))
                    except:
                        logger.warning("Connection appears to be closed, breaking message loop")
                        break
            
            # Clean up tasks
            logger.warning("Message loop ended, cleaning up tasks")
            camera_task.cancel()
            position_task.cancel()
            health_task.cancel()
            flush_task.cancel()
            
            # Wait for tasks to complete with timeout
            try:
                await asyncio.wait_for(asyncio.gather(
                    camera_task, position_task, health_task, flush_task,
                    return_exceptions=True), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not complete in time")
            
            # Wait briefly before reconnecting
            await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            await asyncio.sleep(1)
            
        finally:
            # Always close the websocket
            if websocket:
                try:
                    await websocket.close()
                except:
                    pass
    
    # Final cleanup
    if RUNNING_ON_RPI:
        stop_controller()
        stop_camera()
    
    logger.info("Client shutdown complete")

if __name__ == "__main__":
    try:
        # Run the client
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")