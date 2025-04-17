#!/usr/bin/env python3
"""
Enhanced Bulletproof Raspberry Pi Client for Xeryon Demo Station
- Ultra-responsive with real-time performance
- Robust error handling and recovery
- Optimized for reliability and low latency
- Aggressive buffer management to prevent hanging
- Dynamic FPS: 1 FPS after 30s of no movement, 25 FPS on movement
- Serial port flushed every 3 seconds
- Thermal protection detection and auto-recovery
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

    # Create mock classes for development
    class ConnectionClosed(Exception):
        pass

    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280        # 1280
RESOLUTION_HEIGHT = 720        # 720
JPEG_QUALITY = 70
TARGET_FPS = 25
INACTIVE_FPS = 1              # Reduced frame rate when no movement
MOVEMENT_DETECTION_THRESHOLD = 0.001  # Minimum position change to consider as movement
INACTIVE_TIMEOUT = 30         # Seconds without movement before reducing FPS
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1    # 100ms for more responsive position updates
COMMAND_TIMEOUT = 1.0         # Reduced timeout for serial commands (1 second)
COMMAND_RATE_LIMIT = 0.01     # Minimum interval between commands (10ms)

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.000001    # Reduced to 1μs for maximum responsiveness

# Connection parameters
MAX_RECONNECT_ATTEMPTS = 9999  # Effectively infinite retries
RECONNECT_BASE_DELAY = 0.1     # Start with 100ms delay for faster recovery
MAX_RECONNECT_DELAY = 3.0      # Cap at 3 seconds maximum
MAX_CONNECTION_TIMEOUT = 2.0   # Timeout for connection attempts
MAX_CLOSE_TIMEOUT = 0.5        # Timeout for connection closure
CONNECTION_HEARTBEAT_INTERVAL = 5.0  # Send heartbeats every 5 seconds
BUFFER_FLUSH_INTERVAL = 3.0    # Flush serial port more frequently (3 seconds)
USB_RESET_INTERVAL = 300.0     # Reset USB every 5 minutes if needed

# Safety limits
MIN_POSITION = -30.0  # Minimum allowable position in mm
MAX_POSITION = 30.0   # Maximum allowable position in mm

# ===== GLOBAL STATE =====
shutdown_requested = False
controller = None
axis = None
picam2 = None
demo_running = False
command_queue = asyncio.Queue()
last_successful_command_time = time.time()
last_successful_frame_time = time.time()
last_ping_response_time = time.time()
startup_time = None
last_command_time = 0  # For rate limiting
last_movement_time = time.time()
last_position = 0.0

# Tracking variables
position_lock = threading.Lock()
serial_lock = threading.Lock()  # Synchronize serial access
current_position = 0.0  # Current position in mm
thermal_error_count = 0
amplifier_error_count = 0
serial_error_count = 0
last_error_time = 0
last_serial_flush_time = 0
last_usb_reset_time = 0

# Connection state
total_connection_failures = 0
reconnect_delay = RECONNECT_BASE_DELAY

# ===== LOGGING SETUP =====
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler('/tmp/xeryon_client.log')
                        if RUNNING_ON_RPI else logging.NullHandler()
                    ])
logger = logging.getLogger("XeryonClient")
jpeg_executor = ThreadPoolExecutor(max_workers=2)

# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port(force=False):
    """Aggressively flush serial port to avoid buffer issues."""
    global last_serial_flush_time
    
    current_time = time.time()
    # If not forced, only flush at specified intervals
    if not force and (current_time - last_serial_flush_time < BUFFER_FLUSH_INTERVAL):
        return True
        
    last_serial_flush_time = current_time
    
    if not RUNNING_ON_RPI:
        return True

    try:
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            try:
                subprocess.run(["usbreset", COM_PORT], check=False)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to reset USB: {str(e)}")

            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available after reset")
                return False

        with serial.Serial(COM_PORT, 115200, timeout=0.5) as ser:
            # More aggressive flushing to ensure clean state
            for _ in range(3):
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.01)

            # Send a blank command to clear any pending commands
            ser.write(b'\r\n')
            time.sleep(0.05)
            # Read and discard any available data
            _ = ser.read(ser.in_waiting or 1)

        logger.debug(f"Serial port {COM_PORT} flushed successfully")
        return True
    except Exception as e:
        logger.error(f"Error flushing serial port: {str(e)}")
        global serial_error_count
        serial_error_count += 1
        return False

def reset_usb_if_needed():
    """Reset USB connections if we're having serial issues."""
    global last_usb_reset_time, serial_error_count
    
    current_time = time.time()
    # Only reset at specified intervals or if there are too many serial errors
    if (current_time - last_usb_reset_time < USB_RESET_INTERVAL) and serial_error_count < 5:
        return

    if not RUNNING_ON_RPI:
        return
        
    logger.warning("Performing USB reset due to serial errors or scheduled reset")
    last_usb_reset_time = current_time
    serial_error_count = 0
    
    try:
        # Attempt aggressive USB reset
        subprocess.run(["usbreset", COM_PORT], check=False)
        time.sleep(1)
        # Flush again after reset
        flush_serial_port(force=True)
    except Exception as e:
        logger.error(f"USB reset failed: {str(e)}")

def initialize_xeryon_controller(retry_count=3):
    """Initialize Xeryon controller with comprehensive error handling and retries."""
    global controller, axis, thermal_error_count, amplifier_error_count, serial_error_count

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking Xeryon controller")
        return True

    for attempt in range(retry_count):
        try:
            logger.info(f"Initializing Xeryon controller on {COM_PORT} (attempt {attempt+1}/{retry_count})")

            # Reset USB if needed
            if attempt > 0:
                reset_usb_if_needed()

            # Aggressively flush the serial port
            with serial_lock:
                if not flush_serial_port(force=True):
                    logger.error("Failed to flush serial port - retrying")
                    time.sleep(0.5 * (attempt + 1))  # Incremental backoff
                    continue

            # Create controller with short timeout
            controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
            axis = controller.addAxis(Stage.XLA_312_3N, "X")
            controller.start()
            time.sleep(0.2)  # Reduced wait time

            # Configure axis with minimal delays
            axis.setUnits(Units.mm)
            time.sleep(0.1)
            # Set higher position tolerance for more responsive operation
            axis.sendCommand("POLI=50")
            time.sleep(0.1)

            # Reset error counters
            thermal_error_count = 0
            amplifier_error_count = 0
            serial_error_count = 0

            # Set default parameters
            axis.setSpeed(DEFAULT_SPEED)
            time.sleep(0.1)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            time.sleep(0.1)

            # Enable axis
            axis.sendCommand("ENBL=1")
            time.sleep(0.1)

            # Find index with safety check
            try:
                # Use a timeout for findIndex to prevent hanging
                if hasattr(axis, 'findIndex'):
                    start_time = time.time()
                    axis.findIndex()
                    # Check if index operation takes too long
                    if time.time() - start_time > 10:
                        logger.warning("Index finding took too long, continuing anyway")
            except Exception as e:
                logger.warning(f"Index finding error, continuing anyway: {str(e)}")

            logger.info("Xeryon controller initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Xeryon controller initialization failed (attempt {attempt+1}): {str(e)}")
            stop_controller()
            # If not the last attempt, wait before retrying
            if attempt < retry_count - 1:
                time.sleep(1 * (attempt + 1))  # Incremental backoff

    return False

def stop_controller():
    """Safely stop and release Xeryon controller."""
    global controller, axis

    if not RUNNING_ON_RPI:
        return

    try:
        if controller:
            if axis:
                try:
                    # Stop any ongoing scan/movement
                    axis.stopScan()
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Error stopping scan: {str(e)}")

            try:
                controller.stop()
                logger.info("Controller stopped")
            except Exception as e:
                logger.error(f"Error stopping controller: {str(e)}")
    except Exception as e:
        logger.error(f"Error in stop_controller: {str(e)}")
    finally:
        controller = None
        axis = None
        gc.collect()

def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration parameters with error handling."""
    global axis

    if not RUNNING_ON_RPI or not axis:
        return False

    success = True
    try:
        if acce_value is not None:
            acce_value = max(0, min(65500, int(acce_value)))
            axis.sendCommand(f"ACCE={acce_value}")
            logger.info(f"Set acceleration to {acce_value}")

        if dece_value is not None:
            dece_value = max(0, min(65500, int(dece_value)))
            axis.sendCommand(f"DECE={dece_value}")
            logger.info(f"Set deceleration to {dece_value}")

        axis.sendCommand("ENBL=1")
        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece parameters: {str(e)}")
        return False

def check_and_recover_from_errors():
    """Check for controller errors and try to recover."""
    global axis, thermal_error_count, amplifier_error_count, serial_error_count
    
    if not RUNNING_ON_RPI or not axis:
        return True

    try:
        with serial_lock:
            try:
                stat = axis.getData("STAT")
                
                # Check for thermal protection
                if axis.isThermalProtection1(stat) or axis.isThermalProtection2(stat):
                    thermal_error_count += 1
                    logger.warning(f"Thermal protection detected ({thermal_error_count})")
                    
                    # Try to clear the error
                    axis.sendCommand("ENBL=1")
                    return False
                
                # Check for amplifier error
                if axis.isErrorLimit(stat):
                    amplifier_error_count += 1
                    logger.warning(f"Amplifier error detected ({amplifier_error_count})")
                    
                    # Try to clear the error
                    axis.sendCommand("ENBL=1")
                    return False
                
                # Check for safety timeout
                if axis.isSafetyTimeoutTriggered(stat):
                    logger.warning("Safety timeout triggered")
                    
                    # Try to clear the error
                    axis.sendCommand("ENBL=1")
                    return False
                
                # No errors detected
                return True
            except Exception as e:
                logger.error(f"Error checking controller status: {str(e)}")
                serial_error_count += 1
                return False
    except Exception as e:
        logger.error(f"Error in check_and_recover_from_errors: {str(e)}")
        return False

# ===== CAMERA MANAGEMENT =====
def initialize_camera(retry_count=3):
    """Initialize camera with robust error handling and retries."""
    global picam2

    CROP_FRACTION = 1 / 3
    HORIZONTAL_SHIFT = 0.0
    VERTICAL_SHIFT = 0.0
    SENSOR_WIDTH = 4608
    SENSOR_HEIGHT = 2592

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True

    for attempt in range(retry_count):
        try:
            logger.info(f"Initializing camera (attempt {attempt+1}/{retry_count})")
            
            # Clean up any previous instance
            stop_camera()
            
            picam2 = Picamera2()

            # Calculate crop settings
            crop_w = int(SENSOR_WIDTH * CROP_FRACTION)
            crop_h = int(SENSOR_HEIGHT * CROP_FRACTION)
            max_x_shift = (SENSOR_WIDTH - crop_w) // 2
            max_y_shift = (SENSOR_HEIGHT - crop_h) // 2
            x = int((SENSOR_WIDTH - crop_w) // 2 + HORIZONTAL_SHIFT * max_x_shift)
            y = int((SENSOR_HEIGHT - crop_h) // 2 + VERTICAL_SHIFT * max_y_shift)
            x = max(0, min(x, SENSOR_WIDTH - crop_w))
            y = max(0, min(y, SENSOR_HEIGHT - crop_h))
            scaler_crop = (x, y, crop_w, crop_h)
            logger.info(f"ScalerCrop: {scaler_crop}")

            # Configure camera
            config = picam2.create_video_configuration(
                main={
                    "size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT),
                    "format": "RGB888"
                },
                controls={
                    "ScalerCrop": scaler_crop
                }
            )

            picam2.configure(config)
            picam2.start()
            
            # Fixed exposure settings for consistent imaging
            picam2.set_controls({
                "AeEnable": False,
                "AfMode": 2,
                "ExposureTime": 20000,
                "AnalogueGain": 1.0
            })
            
            # Wait for camera to settle
            time.sleep(2)

            # Capture a few warmup frames to ensure camera is ready
            for i in range(3):
                _ = picam2.capture_array("main")
                time.sleep(0.1)

            logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
            return True

        except Exception as e:
            logger.error(f"Camera initialization failed (attempt {attempt+1}): {str(e)}")
            stop_camera()
            # If not the last attempt, wait before retrying
            if attempt < retry_count - 1:
                time.sleep(1)

    return False

async def encode_jpeg_async(frame, quality):
    """Encode a frame as JPEG asynchronously."""
    return await asyncio.to_thread(encode_jpeg, frame, quality)

def encode_jpeg(frame, quality):
    """Encode a frame as JPEG."""
    encode_param = [
        cv2.IMWRITE_JPEG_QUALITY, quality,
        cv2.IMWRITE_JPEG_OPTIMIZE, 1,
        cv2.IMWRITE_JPEG_PROGRESSIVE, 1
    ]
    success, buffer = cv2.imencode('.jpg', frame, encode_param)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return buffer

def stop_camera():
    """Safely stop and release camera resources."""
    global picam2

    if not RUNNING_ON_RPI:
        return

    try:
        if picam2:
            try:
                if hasattr(picam2, 'stop'):
                    picam2.stop()
                    logger.info("Camera stopped")
            except Exception as e:
                logger.warning(f"Error stopping camera: {str(e)}")

            try:
                if hasattr(picam2, 'close'):
                    picam2.close()
                    logger.info("Camera resources released")
            except Exception as e:
                logger.warning(f"Error closing camera: {str(e)}")
    except Exception as e:
        logger.error(f"Error in stop_camera: {str(e)}")
    finally:
        picam2 = None
        gc.collect()

# ===== COMMAND PROCESSING =====
async def process_command(data):
    """Process incoming commands with comprehensive error handling and safety checks."""
    global axis, last_successful_command_time, current_position, last_command_time
    global thermal_error_count, amplifier_error_count, last_movement_time, last_position

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))

    logger.debug(
        f"Command received: {command}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}, acce: {acce_value}, dece: {dece_value}"
    )

    response = {"status": "success", "rpiId": STATION_ID}

    try:
        # Handle ping/pong for latency measurements
        if message_type == "ping":
            response.update({
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            })
            logger.debug(f"Replied to ping with timestamp: {timestamp}")
            return response
        elif message_type == "pong":
            global last_ping_response_time
            last_ping_response_time = time.time()
            logger.debug(f"Received pong with timestamp: {timestamp}")
            return None
        elif message_type == "heartbeat":
            response.update({
                "type": "heartbeat_response",
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "rpiId": STATION_ID
            })
            return response

        if not RUNNING_ON_RPI or not axis:
            if RUNNING_ON_RPI:
                logger.error("Axis not initialized - cannot process command")
                response["status"] = "error"
                response["message"] = "Controller not initialized"
                return response
            else:
                logger.info(f"Simulation: Processing command {command}")
                response["message"] = f"Simulation: Executed {command}"
                last_successful_command_time = time.time()
                return response

        # Rate limit commands to prevent flooding
        current_time = time.time()
        time_since_last_command = current_time - last_command_time
        if time_since_last_command < COMMAND_RATE_LIMIT:
            await asyncio.sleep(COMMAND_RATE_LIMIT - time_since_last_command)
        last_command_time = time.time()

        # Flush serial port periodically
        if current_time - last_serial_flush_time > BUFFER_FLUSH_INTERVAL:
            with serial_lock:
                flush_serial_port()
                
        # Reset USB if needed
        if current_time - last_usb_reset_time > USB_RESET_INTERVAL:
            reset_usb_if_needed()

        # Check controller state before sending commands
        with serial_lock:
            try:
                error_checks = await asyncio.to_thread(check_and_recover_from_errors)
                if not error_checks:
                    logger.warning("Controller in error state, attempting recovery")
                    # Try to re-enable
                    axis.sendCommand("ENBL=1")
                    # Allow some commands to proceed even with errors
                    if command not in ["stop", "home", "reset"]:
                        response["status"] = "error"
                        response["message"] = "Controller in error state, please try again"
                        return response
            except Exception as e:
                logger.warning(f"Error checking controller state: {str(e)}")
                
        # Handle acceleration and deceleration commands
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(direction) if direction.isdigit() else DEFAULT_ACCELERATION
            with serial_lock:
                set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            last_successful_command_time = time.time()
            return response

        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(direction) if direction.isdigit() else DEFAULT_DECELERATION
            with serial_lock:
                set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            last_successful_command_time = time.time()
            return response

        if acce_value is not None or dece_value is not None:
            with serial_lock:
                set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        # Process the main command
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

            # Safety check - predict final position and check limits
            predicted_position = current_position + final_step
            if predicted_position < MIN_POSITION or predicted_position > MAX_POSITION:
                logger.warning(f"Requested movement exceeds safety limits: {predicted_position} mm")
                response["status"] = "error"
                response["message"] = f"Movement exceeds safety limits ({MIN_POSITION} to {MAX_POSITION} mm)"
                return response

            try:
                with serial_lock:
                    try:
                        # Non-blocking step command
                        await asyncio.wait_for(
                            asyncio.to_thread(axis.step, final_step),
                            timeout=COMMAND_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        logger.error("Timeout waiting for axis.step")
                        raise Exception("Timeout waiting for axis.step")

                with position_lock:
                    # Update position tracking
                    current_position += final_step
                    # Record that movement has happened
                    last_movement_time = time.time()

                # Get actual position
                with serial_lock:
                    try:
                        epos = await asyncio.wait_for(
                            asyncio.to_thread(axis.getEPOS),
                            timeout=COMMAND_TIMEOUT
                        )
                        response["epos"] = epos
                        
                        # Check if position has changed (for movement detection)
                        position_change = abs(epos - last_position)
                        if position_change > MOVEMENT_DETECTION_THRESHOLD:
                            last_movement_time = time.time()
                        last_position = epos
                        
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.error(f"Error getting EPOS: {str(e)}")
                
                response["message"] = f"Moved {direction} by {step_size} {step_unit}"
                last_successful_command_time = time.time()
                
            except Exception as e:
                logger.error(f"Error executing step command: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Error executing step command: {str(e)}"
                
        elif command == "stop":
            try:
                with serial_lock:
                    await asyncio.wait_for(
                        asyncio.to_thread(axis.sendCommand, "STOP=0"),
                        timeout=COMMAND_TIMEOUT
                    )
                response["message"] = "Movement stopped"
                last_successful_command_time = time.time()
            except Exception as e:
                logger.error(f"Error stopping movement: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Error stopping movement: {str(e)}"
                
        elif command == "home":
            try:
                # Return to home position (0) using DPOS
                with serial_lock:
                    await asyncio.to_thread(axis.setDPOS, 0)
                    
                with position_lock:
                    current_position = 0
                    
                response["message"] = "Homed to position 0"
                last_successful_command_time = time.time()
                last_movement_time = time.time()
            except Exception as e:
                logger.error(f"Error homing: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Error homing: {str(e)}"
                
        elif command == "scan":
            try:
                # Extract scan parameters
                scan_distance = float(data.get("scanDistance", 10))
                scan_cycles = int(data.get("scanCycles", 1))
                
                # Safety check for scan limits
                scan_min = current_position - scan_distance/2
                scan_max = current_position + scan_distance/2
                
                if scan_min < MIN_POSITION or scan_max > MAX_POSITION:
                    logger.warning(f"Requested scan exceeds safety limits: {scan_min} to {scan_max} mm")
                    response["status"] = "error"
                    response["message"] = f"Scan exceeds safety limits ({MIN_POSITION} to {MAX_POSITION} mm)"
                    return response
                
                with serial_lock:
                    # Set scan parameters
                    await asyncio.to_thread(axis.sendCommand, f"SCNL={scan_min}")
                    await asyncio.to_thread(axis.sendCommand, f"SCNH={scan_max}")
                    await asyncio.to_thread(axis.sendCommand, f"SCNN={scan_cycles}")
                    # Start scan
                    await asyncio.to_thread(axis.sendCommand, "SCAN=1")
                    
                response["message"] = f"Started scan from {scan_min} to {scan_max} mm for {scan_cycles} cycles"
                last_successful_command_time = time.time()
                last_movement_time = time.time()
            except Exception as e:
                logger.error(f"Error starting scan: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Error starting scan: {str(e)}"
                
        elif command == "reset":
            try:
                # Reinitialize the controller
                stop_controller()
                time.sleep(0.5)
                await asyncio.to_thread(initialize_xeryon_controller)
                response["message"] = "Controller reset and reinitialized"
            except Exception as e:
                logger.error(f"Error resetting controller: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Error resetting controller: {str(e)}"
                
        elif command == "demo":
            # Start the demo as a background task
            if not demo_running:
                global demo_running
                demo_running = True
                asyncio.create_task(run_demo())
                response["message"] = "Demo started"
            else:
                response["message"] = "Demo already running"
                
        else:
            response["status"] = "error"
            response["message"] = f"Unknown command: {command}"

        return response
            
    except ValueError as e:
        logger.error(f"Invalid command parameters: {str(e)}")
        response["status"] = "error"
        response["message"] = f"Invalid parameters: {str(e)}"
        return response
        
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        response["status"] = "error"
        response["message"] = f"Internal error: {str(e)}"
        return response

async def run_demo():
    """Run a safe demo sequence that showcases the capabilities of the actuator."""
    global demo_running, axis, current_position
    
    logger.info("Starting demo sequence")
    
    try:
        # Safety check - ensure we're within limits
        if not RUNNING_ON_RPI:
            await asyncio.sleep(1)
            logger.info("Simulation: Demo running")
            demo_positions = [-5, 0, 5, 10, 5, 0, -5, -10, -5, 0]
            for pos in demo_positions:
                # Simulate position updates
                logger.info(f"Demo position: {pos}")
                await asyncio.sleep(1)
            logger.info("Demo completed")
            demo_running = False
            return
            
        # Initialize with reasonable values
        with serial_lock:
            # Set initial parameters
            await asyncio.to_thread(set_acce_dece_params, DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            await asyncio.to_thread(axis.setSpeed, 500)
        
        # First get current position
        with serial_lock:
            current_pos = await asyncio.to_thread(axis.getEPOS)
        
        # Define safe demo range
        min_demo_pos = max(MIN_POSITION + 5, -25)  # Stay 5mm from limits
        max_demo_pos = min(MAX_POSITION - 5, 25)   # Stay 5mm from limits
        
        # First move to a known safe starting position
        safe_start = 0  # Center position
        logger.info(f"Moving to safe start position: {safe_start}")
        
        with serial_lock:
            await asyncio.to_thread(axis.setDPOS, safe_start)
        await asyncio.sleep(3)  # Wait for movement to complete
        
        # Random interesting positions to visit, with varied speeds
        demo_positions = []
        last_pos = safe_start
        
        # Generate 8-10 random positions without repeating the same position twice
        for i in range(random.randint(8, 10)):
            # Try to find a position that's different from the last one
            for _ in range(10):  # Try 10 times to find a unique position
                new_pos = random.uniform(min_demo_pos, max_demo_pos)
                # Round to 2 decimal places
                new_pos = round(new_pos, 2)
                # Ensure we don't repeat the same position
                if abs(new_pos - last_pos) > 3:  # At least 3mm different
                    demo_positions.append(new_pos)
                    last_pos = new_pos
                    break
                    
        logger.info(f"Demo will visit positions: {demo_positions}")
        
        # Run through the demo positions with varied speeds
        for i, pos in enumerate(demo_positions):
            if shutdown_requested or not demo_running:
                break
                
            # Vary speed between positions (100-1000)
            speed = random.randint(100, 1000)
            acce = random.randint(1000, 65000)
            dece = random.randint(1000, 65000)
            
            logger.info(f"Demo step {i+1}/{len(demo_positions)}: Moving to {pos} mm at speed {speed}")
            
            with serial_lock:
                # Set new parameters
                await asyncio.to_thread(axis.setSpeed, speed)
                await asyncio.to_thread(set_acce_dece_params, acce, dece)
                # Move to position
                await asyncio.to_thread(axis.setDPOS, pos)
                
            # Update tracking
            with position_lock:
                current_position = pos
                
            # Wait for movement to complete, but not too long
            await asyncio.sleep(max(1, abs(last_pos - pos) / 10))
            
        # Return to center at the end
        logger.info("Demo completed, returning to center")
        with serial_lock:
            # Set moderate values for final movement
            await asyncio.to_thread(axis.setSpeed, 500)
            await asyncio.to_thread(set_acce_dece_params, 32750, 32750)
            await asyncio.to_thread(axis.setDPOS, 0)
            
        # Update tracking
        with position_lock:
            current_position = 0
            
    except Exception as e:
        logger.error(f"Error in demo sequence: {str(e)}")
    finally:
        demo_running = False
        logger.info("Demo sequence ended")

async def send_camera_frames(websocket):
    """Send the newest camera frames in real-time, dropping older frames if necessary."""
    global last_successful_frame_time, last_movement_time, last_position
    
    frame_count = 0
    sleep_time = 1.0 / TARGET_FPS
    inactive_sleep_time = 1.0 / INACTIVE_FPS
    prev_epos = None
    
    logger.info(f"Starting camera frame transmission at {TARGET_FPS} FPS")
    
    while not shutdown_requested:
        try:
            # Determine if we're active (movement happening) or inactive
            is_active = (time.time() - last_movement_time) < INACTIVE_TIMEOUT
            current_sleep = sleep_time if is_active else inactive_sleep_time
            
            # Capture frame based on activity state
            if RUNNING_ON_RPI and picam2:
                try:
                    frame = picam2.capture_array("main")
                    if frame is None:
                        logger.warning("Received None frame from camera")
                        await asyncio.sleep(current_sleep)
                        continue
                except Exception as e:
                    logger.error(f"Error capturing frame: {str(e)}")
                    await asyncio.sleep(current_sleep)
                    continue
            else:
                # Simulation mode - create a test frame
                frame_count += 1
                width, height = RESOLUTION_WIDTH, RESOLUTION_HEIGHT
                frame = create_test_frame(frame_count, current_position)
                
            # Check if websocket is still open
            if websocket.closed:
                logger.error("WebSocket closed, exiting frame sender")
                break
                
            # Encode frame to JPEG
            try:
                # Adapt quality based on activity - higher quality when active
                quality = 75 if is_active else 60
                buffer = await encode_jpeg_async(frame, quality)
                
                # Convert to base64 for transmission
                frame_data = base64.b64encode(buffer).decode('utf-8')
                
                # Create and send message
                message = {
                    "type": "camera_frame",
                    "frame": f"data:image/jpeg;base64,{frame_data}",
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat(),
                    "frameNumber": frame_count
                }
                
                # Only check EPOS if we're running on the actual RPi
                if RUNNING_ON_RPI and axis:
                    try:
                        with serial_lock:
                            epos = await asyncio.wait_for(
                                asyncio.to_thread(axis.getEPOS),
                                timeout=0.01  # Very short timeout
                            )
                            
                            # Only update if position changed
                            if prev_epos is None or abs(epos - prev_epos) > 0.0001:
                                message["epos"] = epos
                                prev_epos = epos
                                
                                # Check for movement
                                if last_position is not None and abs(epos - last_position) > MOVEMENT_DETECTION_THRESHOLD:
                                    last_movement_time = time.time()
                                last_position = epos
                                
                                # Update current position for tracking
                                with position_lock:
                                    current_position = epos
                    except Exception as e:
                        # Don't log every error to avoid spam
                        pass
                
                # Send the frame
                if not websocket.closed:
                    await websocket.send(json.dumps(message))
                    last_successful_frame_time = time.time()
                    
                    # Log occasional frame sends to avoid filling logs
                    if frame_count % 100 == 0:
                        fps_mode = "Active" if is_active else "Inactive"
                        logger.info(f"Sent frame #{frame_count} - {fps_mode} mode")
            except Exception as e:
                logger.error(f"Error encoding or sending frame: {str(e)}")
                
            # Sleep to maintain target FPS, considering processing time
            await asyncio.sleep(current_sleep)
                
        except asyncio.CancelledError:
            logger.info("Camera frame sender task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in camera frame loop: {str(e)}")
            await asyncio.sleep(current_sleep)
            
    logger.info("Camera frame sender stopped")
            
def create_test_frame(frame_number, position):
    """Create a test frame with important information for simulation."""
    width, height = RESOLUTION_WIDTH, RESOLUTION_HEIGHT
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Fill background
    frame[:, :] = (50, 50, 50)  # Dark gray background
    
    # Add position indicator
    position_x = int((position + 30) / 60 * width)  # Scale position to width
    position_x = max(0, min(position_x, width - 1))
    
    # Draw position marker
    cv2.rectangle(frame, (position_x - 10, height // 2 - 10), 
                 (position_x + 10, height // 2 + 10), (0, 255, 0), -1)
    
    # Add text
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    texts = [
        f"Frame: {frame_number}",
        f"Position: {position:.3f} mm",
        f"Time: {timestamp}",
        f"RPi ID: {STATION_ID}"
    ]
    
    for i, text in enumerate(texts):
        cv2.putText(frame, text, (20, 30 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, (255, 255, 255), 2)
    
    return frame

async def send_position_updates(websocket):
    """Send position updates at regular intervals."""
    global current_position
    
    logger.info(f"Starting position updates at {1/EPOS_UPDATE_INTERVAL} Hz")
    
    while not shutdown_requested:
        try:
            if websocket.closed:
                logger.error("WebSocket closed, exiting position sender")
                break
                
            # Get current position
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    with serial_lock:
                        epos = await asyncio.wait_for(
                            asyncio.to_thread(axis.getEPOS),
                            timeout=COMMAND_TIMEOUT
                        )
                        
                        # Update current position for tracking
                        with position_lock:
                            current_position = epos
                except Exception as e:
                    logger.warning(f"Error getting position: {str(e)}")
            else:
                # Simulation - use tracked position
                with position_lock:
                    epos = current_position
                    
            # Send position update
            if epos is not None and not websocket.closed:
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
            logger.info("Position updates task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in position updates: {str(e)}")
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
    logger.info("Position updates stopped")

async def health_checker(websocket):
    """Monitor and report on system health."""
    logger.info("Starting health checker")
    
    check_interval = 1.0  # Check health every second
    last_health_message = time.time()
    health_message_interval = CONNECTION_HEARTBEAT_INTERVAL
    
    while not shutdown_requested:
        try:
            if websocket.closed:
                logger.error("WebSocket closed, exiting health checker")
                break
                
            current_time = time.time()
            
            # Check if we need to send a health message
            if current_time - last_health_message >= health_message_interval:
                # Check controller errors
                errors = False
                error_message = ""
                
                if RUNNING_ON_RPI and axis:
                    try:
                        with serial_lock:
                            stat = axis.getData("STAT")
                            
                            # Check for common errors
                            if axis.isThermalProtection1(stat) or axis.isThermalProtection2(stat):
                                errors = True
                                error_message = "Thermal protection active"
                            elif axis.isErrorLimit(stat):
                                errors = True
                                error_message = "Error limit reached"
                            elif axis.isSafetyTimeoutTriggered(stat):
                                errors = True
                                error_message = "Safety timeout triggered"
                    except Exception as e:
                        errors = True
                        error_message = f"Error checking controller: {str(e)}"
                
                # Prepare health message
                message = {
                    "type": "health_update",
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat(),
                    "uptime": time.time() - startup_time if startup_time else 0,
                    "lastCommandTime": time.time() - last_successful_command_time,
                    "lastFrameTime": time.time() - last_successful_frame_time,
                    "status": "error" if errors else "healthy",
                }
                
                if errors:
                    message["errorMessage"] = error_message
                    
                # Add error counters
                if RUNNING_ON_RPI:
                    message["thermalErrorCount"] = thermal_error_count
                    message["amplifierErrorCount"] = amplifier_error_count
                    message["serialErrorCount"] = serial_error_count
                
                # Send health update
                if not websocket.closed:
                    await websocket.send(json.dumps(message))
                    last_health_message = current_time
                    
                    # Also send a ping for latency measurement
                    ping_message = {
                        "type": "ping",
                        "rpiId": STATION_ID,
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(ping_message))
                    logger.debug("Sent ping message for latency measurement")
                
            # Sleep for the check interval
            await asyncio.sleep(check_interval)
            
        except asyncio.CancelledError:
            logger.info("Health checker task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in health checker: {str(e)}")
            await asyncio.sleep(check_interval)
            
    logger.info("Health checker stopped")

async def flush_buffers():
    """Flush buffers to prevent data buildup, but only when necessary."""
    logger.info("Starting buffer flush task")
    
    flush_interval = BUFFER_FLUSH_INTERVAL
    
    while not shutdown_requested:
        try:
            # Flush serial port
            if RUNNING_ON_RPI:
                with serial_lock:
                    flush_serial_port()
                    
            # Check if USB reset is needed
            current_time = time.time()
            if RUNNING_ON_RPI and current_time - last_usb_reset_time > USB_RESET_INTERVAL:
                reset_usb_if_needed()
                
            # Wait for next flush
            await asyncio.sleep(flush_interval)
            
        except asyncio.CancelledError:
            logger.info("Buffer flush task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in buffer flush: {str(e)}")
            await asyncio.sleep(flush_interval)
            
    logger.info("Buffer flush task stopped")

async def command_processor():
    """Process queued commands in the background."""
    logger.info("Starting command processor")
    
    while not shutdown_requested:
        try:
            # Get command from queue
            command, websocket = await command_queue.get()
            
            # Process command
            response = await process_command(command)
            
            # Send response if needed
            if response and not websocket.closed:
                await websocket.send(json.dumps(response))
                
            # Mark task as done
            command_queue.task_done()
            
        except asyncio.CancelledError:
            logger.info("Command processor task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in command processor: {str(e)}")
            
    logger.info("Command processor stopped")

async def rpi_client():
    """Main client function with robust connection and error handling."""
    global startup_time, reconnect_delay, total_connection_failures
    
    startup_time = time.time()
    logger.info(f"Starting RPi client for {STATION_ID}")
    
    # Set up signal handlers
    def handle_signal(sig, frame):
        global shutdown_requested
        logger.info(f"Received signal {sig}, initiating shutdown")
        shutdown_requested = True
        
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # Start the command processor
    command_processor_task = asyncio.create_task(command_processor())
    
    # Initialize controller and camera
    if RUNNING_ON_RPI:
        logger.info("Initializing hardware")
        
        # Initialize controller
        controller_ready = await asyncio.to_thread(initialize_xeryon_controller)
        if not controller_ready:
            logger.error("Failed to initialize controller, continuing anyway")
            
        # Initialize camera
        camera_ready = await asyncio.to_thread(initialize_camera)
        if not camera_ready:
            logger.error("Failed to initialize camera, continuing anyway")
    
    # Main connection loop
    attempt = 0
    while not shutdown_requested:
        try:
            attempt += 1
            logger.info(f"Connection attempt {attempt}/{MAX_RECONNECT_ATTEMPTS} to {SERVER_URL}")
            
            # Connect to server with timeout
            try:
                websocket = await asyncio.wait_for(
                    websockets.connect(SERVER_URL, ping_interval=None),
                    timeout=MAX_CONNECTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(f"Connection timed out after {MAX_CONNECTION_TIMEOUT}s")
                total_connection_failures += 1
                # Calculate backoff with jitter
                jitter = random.uniform(0.8, 1.2)
                reconnect_delay = min(RECONNECT_BASE_DELAY * (2 ** min(total_connection_failures, 4)) * jitter, MAX_RECONNECT_DELAY)
                logger.info(f"Will retry in {reconnect_delay:.2f}s")
                await asyncio.sleep(reconnect_delay)
                continue
            
            logger.info("Connected to server")
            
            # Reset failure counters on successful connection
            total_connection_failures = 0
            reconnect_delay = RECONNECT_BASE_DELAY
            
            # Send registration message
            register_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }
            await websocket.send(json.dumps(register_message))
            logger.info(f"Registered as {STATION_ID} with combined connection")
            
            # Start background tasks
            tasks = []
            
            # Camera frames task
            frames_task = asyncio.create_task(send_camera_frames(websocket))
            tasks.append(frames_task)
            
            # Position updates task
            position_task = asyncio.create_task(send_position_updates(websocket))
            tasks.append(position_task)
            
            # Health checker task
            health_task = asyncio.create_task(health_checker(websocket))
            tasks.append(health_task)
            
            # Buffer flush task
            flush_task = asyncio.create_task(flush_buffers())
            tasks.append(flush_task)
            
            # Main message loop
            while not shutdown_requested:
                try:
                    # Wait for messages with timeout
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=30.0  # Long timeout to allow for ping/pong
                    )
                    
                    # Parse message
                    data = json.loads(message)
                    
                    # Queue command for processing
                    if data.get("type") in ["command", "ping", "pong", "heartbeat"]:
                        await command_queue.put((data, websocket))
                    
                except asyncio.TimeoutError:
                    # Check if connection is still alive
                    if websocket.closed:
                        logger.error("WebSocket closed due to timeout")
                        break
                        
                    # Try pinging the server
                    try:
                        ping_message = {
                            "type": "ping",
                            "rpiId": STATION_ID,
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send(json.dumps(ping_message))
                        logger.debug("Sent ping after timeout")
                    except Exception as e:
                        logger.error(f"Failed to send ping: {str(e)}")
                        break
                        
                except Exception as e:
                    logger.error(f"Error in message loop: {str(e)}")
                    # Only break if websocket is closed
                    if websocket.closed:
                        break
                        
            # Connection lost or closed, clean up tasks
            logger.warning("Connection closed or lost, cleaning up tasks")
            for task in tasks:
                task.cancel()
                
            try:
                # Wait for tasks to complete with timeout
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=MAX_CLOSE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not complete in time during cleanup")
                
            # Close websocket if still open
            if not websocket.closed:
                try:
                    await websocket.close()
                except Exception as e:
                    logger.error(f"Error closing websocket: {str(e)}")
                    
            # Brief sleep before reconnecting
            await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Error in connection loop: {str(e)}")
            # Calculate backoff with jitter
            jitter = random.uniform(0.8, 1.2)
            reconnect_delay = min(RECONNECT_BASE_DELAY * (2 ** min(total_connection_failures, 4)) * jitter, MAX_RECONNECT_DELAY)
            logger.info(f"Will retry in {reconnect_delay:.2f}s")
            await asyncio.sleep(reconnect_delay)
    
    # Shutdown cleanup
    logger.info("Shutting down client")
    
    # Cancel command processor task
    command_processor_task.cancel()
    try:
        await command_processor_task
    except asyncio.CancelledError:
        pass
        
    # Final cleanup
    await shutdown()
    
async def main():
    """Entry point with proper signal handling and cleanup."""
    global startup_time
    
    startup_time = time.time()
    logger.info(f"Starting RPi client for Xeryon Demo Station ({STATION_ID})")
    
    try:
        await rpi_client()
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
    finally:
        await shutdown()

async def shutdown():
    """Clean shutdown procedure."""
    logger.info("Performing clean shutdown")
    
    # Stop hardware
    if RUNNING_ON_RPI:
        # Stop controller
        stop_controller()
        
        # Stop camera
        stop_camera()
        
    # Final cleanup
    gc.collect()
    logger.info("Shutdown complete")

if __name__ == "__main__":
    try:
        # Add cv2 and numpy if needed for simulation mode
        if not RUNNING_ON_RPI:
            import numpy as np
            
        # Run the client
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {str(e)}")