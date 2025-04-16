#!/usr/bin/env python3
"""
Bulletproof Raspberry Pi Client for Xeryon Demo Station
- Ultra-responsive with real-time performance
- Robust error handling and recovery
- Optimized for reliability and low latency
- Aggressive buffer management to prevent hanging
- Binary WebSocket frames for camera transmission
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
import struct  # Added for binary frame support

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
JPEG_QUALITY = 50
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.2  # 50ms position update interval
COMMAND_TIMEOUT = 60

# Binary WebSocket protocol configuration - NEW FOR BINARY FRAMES
FRAME_HEADER_FORMAT = "<4sII"  # format: 4-char station ID, uint32 frame number, uint32 timestamp
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FORMAT)

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.00001  # Absolute minimum sleep (10μs)

# Connection parameters - Optimized for ultra-fast reconnection
MAX_RECONNECT_ATTEMPTS = 9999  # Effectively infinite retries
RECONNECT_BASE_DELAY = 0.5  # Start with just 500ms delay
MAX_RECONNECT_DELAY = 5.0  # Cap at 5 seconds maximum
MAX_CONNECTION_TIMEOUT = 3.0  # Timeout for connection attempts
MAX_CLOSE_TIMEOUT = 1.0  # Timeout for connection closure
CONNECTION_HEARTBEAT_INTERVAL = 5.0  # Send heartbeats every 5 seconds

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

# Tracking variables
position_lock = threading.Lock()
current_position = 0.0  # Current position in mm
thermal_error_count = 0
amplifier_error_count = 0
serial_error_count = 0
last_error_time = 0

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
jpeg_executor = ThreadPoolExecutor(max_workers=2)  # One thread is often enough, 2 max



# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port():
    """Aggressively flush serial port to avoid buffer issues."""
    if not RUNNING_ON_RPI:
        return True

    try:
        # First check if the COM port exists
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            try:
                subprocess.run(["usbreset", COM_PORT], check=False)
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to reset USB: {str(e)}")

            # Check again after reset attempt
            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available after reset")
                return False

        # Aggressively flush serial buffers
        with serial.Serial(COM_PORT, 115200, timeout=0.5) as ser:
            # Execute multiple flushes
            for _ in range(3):
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.01)

            # Send a harmless command to clear any pending data
            ser.write(b'\r\n')
            time.sleep(0.05)
            # Read and discard any pending data
            _ = ser.read(ser.in_waiting or 1)

        logger.debug(f"Serial port {COM_PORT} flushed successfully")
        return True
    except Exception as e:
        logger.error(f"Error flushing serial port: {str(e)}")
        global serial_error_count
        serial_error_count += 1
        return False


def initialize_xeryon_controller():
    """Initialize Xeryon controller with comprehensive error handling."""
    global controller, axis, thermal_error_count, amplifier_error_count, serial_error_count

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking Xeryon controller")
        return True

    try:
        logger.info(f"Initializing Xeryon controller on {COM_PORT}")

        # First aggressively flush the serial port
        if not flush_serial_port():
            logger.error(
                "Failed to flush serial port - aborting controller init")
            return False

        # Create controller
        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        time.sleep(0.5)  # Allow controller to initialize fully

        # Configure units and basic parameters
        axis.setUnits(Units.mm)
        time.sleep(0.1)
        axis.sendCommand("POLI=50")  # Set polling rate
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

        # Enable controller
        axis.sendCommand("ENBL=1")
        time.sleep(0.1)

        # Home to index
        axis.findIndex()
        logger.info("Xeryon controller initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Xeryon controller initialization failed: {str(e)}")
        stop_controller()
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
                    # Try to gracefully stop any movements
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
            # Ensure acce_value is within valid range (0-65500)
            acce_value = max(0, min(65500, int(acce_value)))
            axis.sendCommand(f"ACCE={acce_value}")
            logger.info(f"Set acceleration to {acce_value}")

        if dece_value is not None:
            # Ensure dece_value is within valid range (0-65500)
            dece_value = max(0, min(65500, int(dece_value)))
            axis.sendCommand(f"DECE={dece_value}")
            logger.info(f"Set deceleration to {dece_value}")

        # To be extra safe, re-enable the controller
        axis.sendCommand("ENBL=1")

        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece parameters: {str(e)}")
        return False

# ===== CAMERA MANAGEMENT =====
def initialize_camera():
    """Initialize camera with robust error handling."""
    global picam2

    # === Adjustable crop settings ===
    CROP_FRACTION = 1 / 3  # Capture 1/5th of full sensor area
    HORIZONTAL_SHIFT = 0.0  # -1.0 (left) to 1.0 (right)
    VERTICAL_SHIFT = 0.0 # -1.0 (up) to 1.0 (down)

    # Full sensor resolution for Pi Camera 3 (IMX708)
    SENSOR_WIDTH = 4608
    SENSOR_HEIGHT = 2592

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True

    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()

        # Calculate crop dimensions
        crop_w = int(SENSOR_WIDTH * CROP_FRACTION)
        crop_h = int(SENSOR_HEIGHT * CROP_FRACTION)

        # Calculate center-based offset
        max_x_shift = (SENSOR_WIDTH - crop_w) // 2
        max_y_shift = (SENSOR_HEIGHT - crop_h) // 2

        x = int((SENSOR_WIDTH - crop_w) // 2 + HORIZONTAL_SHIFT * max_x_shift)
        y = int((SENSOR_HEIGHT - crop_h) // 2 + VERTICAL_SHIFT * max_y_shift)

        # Clamp x and y to valid sensor bounds
        x = max(0, min(x, SENSOR_WIDTH - crop_w))
        y = max(0, min(y, SENSOR_HEIGHT - crop_h))

        scaler_crop = (x, y, crop_w, crop_h)
        logger.info(f"ScalerCrop: {scaler_crop}")

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

        # Enable autofocus
        picam2.set_controls({
            "AeEnable": False,              # Disable auto exposure
            "AfMode": 2,
            "ExposureTime": 20000,         # 20ms = sync with 50Hz lighting
            "AnalogueGain": 1.0            # You can raise this if image too dark
        })        
        time.sleep(2)  # Allow autofocus/exposure/white balance to stabilize

        for i in range(3):
            _ = picam2.capture_array("main")
            time.sleep(0.1)

        logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        return True

    except Exception as e:
        logger.error(f"Camera initialization failed: {str(e)}")
        stop_camera()
        return False


async def encode_jpeg_async(frame, quality):
    return await asyncio.to_thread(encode_jpeg, frame, quality)

def encode_jpeg(frame, quality):
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
            if hasattr(picam2, 'started') and picam2.started:
                try:
                    picam2.stop()
                    logger.info("Camera stopped")
                except Exception as e:
                    logger.warning(f"Error stopping camera: {str(e)}")

            try:
                picam2.close()
                logger.info("Camera resources released")
            except Exception as e:
                logger.warning(f"Error closing camera: {str(e)}")
    except Exception as e:
        logger.error(f"Error in stop_camera: {str(e)}")
    finally:
        picam2 = None
        gc.collect()

# ===== BACKGROUND TASKS =====
async def send_camera_frames(websocket):
    """Send camera frames with real-time optimization, prioritizing freshness."""
    global picam2, last_successful_frame_time

    frame_count = 0
    last_frame_time = time.time()
    frame_backlog = 0
    delay_factor = 1.0  # Dynamically adjusted based on performance
    last_flush_time = time.time()  # Added for regular buffer flushing

    logger.info("Starting camera frame sender task with binary WebSocket frames")

    while not shutdown_requested:
        try:
            # Regular buffer flush to prevent buildup
            current_time = time.time()
            if current_time - last_flush_time > 1.0:  # Flush every second
                if RUNNING_ON_RPI and picam2:
                    try:
                        _ = picam2.capture_array("main")  # Capture and discard to clear buffer
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
                last_flush_time = current_time

            # Check if camera is available
            if not RUNNING_ON_RPI:
                # Simulation mode - generate a colored test pattern
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue

            if not picam2 or not hasattr(picam2,
                                         'started') or not picam2.started:
                logger.warning(
                    "Camera not available - attempting to initialize")
                initialize_camera()
                await asyncio.sleep(1)
                continue

            # Real-time optimization: Calculate timing
            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time

            # Skip frames if we're falling behind to prioritize showing the most current image
            if elapsed > frame_interval * 2:
                frame_backlog += 1
                if frame_backlog % 10 == 0:
                    logger.debug(
                        f"Frame sender falling behind (backlog: {frame_backlog}) - prioritizing freshness"
                    )
                # Don't sleep - capture a fresh frame immediately
            else:
                frame_backlog = max(0, frame_backlog - 1)  # Gradually reduce backlog count

                # Brief sleep if we're ahead of schedule (but keep it minimal)
                if elapsed < frame_interval:
                    # Use a very short sleep to maintain real-time priority
                    await asyncio.sleep(min(frame_interval - elapsed, 0.005) * delay_factor)

            # Take absolute minimal sleep to prevent CPU hogging while maintaining responsiveness
            await asyncio.sleep(MIN_SLEEP_DELAY)

            # Capture frame with error handling
            last_frame_time = time.time()
            try:
                # Capture the frame
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)  # Brief pause on error
                continue

            # Get timestamp and prepare frame
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # Add frame info overlay
            id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
            cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)

            # Add position overlay
            with position_lock:
                pos_str = f"Position: {current_position:.3f} mm"
            cv2.putText(frame, pos_str, (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)

            # Adjust JPEG quality based on backlog (lower quality if falling behind)
            jpeg_quality = JPEG_QUALITY
            if frame_backlog > 5:
                # Reduce quality in steps as backlog increases
                jpeg_quality = max(30,
                                   JPEG_QUALITY - (frame_backlog // 5) * 10)

            # Encode with threaded JPEG encoder
            try:
                buffer = await encode_jpeg_async(frame, jpeg_quality)
                
                # BINARY WEBSOCKET CHANGE: Create binary frame header with WebSocket
                timestamp = int(time.time() * 1000) % 0xFFFFFFFF  # Ensure fits in uint32
                frame_num = frame_count % 0xFFFFFFFF              # Ensure fits in uint32
                
                # Pack header with struct
                header = struct.pack(FRAME_HEADER_FORMAT,
                                   STATION_ID.encode()[:4].ljust(4),  # Ensure 4 chars exactly
                                   frame_num,
                                   timestamp)
                
                # Combine header and JPEG data - NO base64 encoding for binary
                binary_data = header + buffer.tobytes()
                
                # Send as binary WebSocket message
                await websocket.send(binary_data)
                
                frame_count += 1
                last_successful_frame_time = time.time()
                
                # Log only occasionally to reduce overhead
                if frame_count % 30 == 0:
                    logger.debug(f"Sent binary frame {frame_count} at {frame_time}")

                # Dynamically adjust delay factor based on success
                delay_factor = max(0.1, delay_factor * 0.95 +
                                   0.05)  # Slowly increase performance

            except Exception as e:
                logger.error(f"Frame encoding or sending error: {e}")
                delay_factor = min(1.0, delay_factor *
                                   1.2)  # Back off slightly on error
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Camera frame sender error: {str(e)}")
            await asyncio.sleep(0.1)


# ===== COMMAND PROCESSING =====
async def process_command(data):
    """Process incoming commands with comprehensive error handling and safety checks."""
    global axis, last_successful_command_time, current_position
    global thermal_error_count, amplifier_error_count
    axis.sendCommand("ENBL=1")

    # Extract command data
    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")

    # Handle acceleration/deceleration parameters (support both naming conventions)
    acce_value = data.get("acceleration")
    if acce_value is None:
        acce_value = data.get("acce")

    dece_value = data.get("deceleration")
    if dece_value is None:
        dece_value = data.get("dece")

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
            # Heartbeat message for connection health verification
            response.update({
                "type": "heartbeat_response",
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "rpiId": STATION_ID
            })
            return response

        # Verify controller is initialized
        if not RUNNING_ON_RPI or not axis:
            if RUNNING_ON_RPI:  # Only log as error if actually on RPi
                logger.error("Axis not initialized - cannot process command")
                response["status"] = "error"
                response["message"] = "Controller not initialized"
                return response
            else:
                # In simulation mode, we'll pretend commands work
                logger.info(f"Simulation: Processing command {command}")
                response["message"] = f"Simulation: Executed {command}"
                last_successful_command_time = time.time()
                return response

        # Add minimal sleep to prevent CPU hogging while ensuring ultra-responsiveness
        await asyncio.sleep(MIN_SLEEP_DELAY)

        # Always enable controller before commands to prevent thermal protection issues
        try:
            axis.sendCommand("ENBL=1")
        except Exception as e:
            logger.warning(f"Error enabling controller: {str(e)}")

        # Handle acceleration and deceleration commands first
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(
                    direction) if direction.isdigit() else DEFAULT_ACCELERATION
            set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            last_successful_command_time = time.time()
            return response

        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(
                    direction) if direction.isdigit() else DEFAULT_DECELERATION
            set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            last_successful_command_time = time.time()
            return response

        elif command == "speed":
            speed_value = int(data.get('value', DEFAULT_SPEED))
            if speed_value < 1:
                speed_value = 1
            elif speed_value > 5000:
                speed_value = 5000

            axis.setSpeed(speed_value)
            logger.info(f"Speed set to {speed_value}")
            response["message"] = f"Speed set to {speed_value}"
            last_successful_command_time = time.time()
            return response

        # Convert step size to mm if using other units
        step_size_mm = step_size
        if step_unit == "μm":
            step_size_mm = step_size / 1000.0
        elif step_unit == "nm":
            step_size_mm = step_size / 1000000.0

        # Handle motion commands
        if command == "step":
            # Get current position
            with position_lock:
                current_pos = current_position
                try:
                    current_pos = axis.getPos()
                except Exception as e:
                    logger.warning(f"Error getting position: {str(e)}")

            # Calculate target position
            if direction == "left":
                target_pos = current_pos - step_size_mm
            elif direction == "right":
                target_pos = current_pos + step_size_mm
            else:
                response["status"] = "error"
                response["message"] = f"Invalid direction: {direction}"
                return response

            # Safety limits - ensure we don't exceed -30mm to +30mm range
            if target_pos < -30:
                target_pos = -30
                logger.warning(f"Limiting target position to {target_pos}mm (lower bound)")
            elif target_pos > 30:
                target_pos = 30
                logger.warning(f"Limiting target position to {target_pos}mm (upper bound)")

            # Execute step
            try:
                axis.moveTo(target_pos)
                response["message"] = f"Stepped to {target_pos} mm"
                last_successful_command_time = time.time()

                # Update the current position
                with position_lock:
                    current_position = axis.getPos()

                return response
            except Exception as e:
                logger.error(f"Error executing step: {str(e)}")
                error_str = str(e).lower()

                # Check for specific errors
                if "thermal protection" in error_str:
                    thermal_error_count += 1
                    logger.critical(f"THERMAL PROTECTION ERROR {thermal_error_count}")
                    response["status"] = "error"
                    response["message"] = "Thermal protection active - motor disabled"
                elif "amplifier" in error_str:
                    amplifier_error_count += 1
                    logger.critical(f"AMPLIFIER ERROR {amplifier_error_count}")
                    response["status"] = "error"
                    response["message"] = "Amplifier error - check controller"
                else:
                    response["status"] = "error"
                    response["message"] = f"Step error: {str(e)}"

                return response

        elif command == "home":
            try:
                # Move to 0.0mm position
                axis.moveTo(0.0)
                response["message"] = "Moving to home position (0.0mm)"
                last_successful_command_time = time.time()

                # Update the current position
                with position_lock:
                    current_position = axis.getPos()

                return response
            except Exception as e:
                logger.error(f"Error homing: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Home error: {str(e)}"
                return response

        elif command == "stop":
            try:
                # Stop movement
                axis.stopMove()
                response["message"] = "Movement stopped"
                last_successful_command_time = time.time()

                # Update the current position
                with position_lock:
                    current_position = axis.getPos()

                return response
            except Exception as e:
                logger.error(f"Error stopping: {str(e)}")
                response["status"] = "error"
                response["message"] = f"Stop error: {str(e)}"
                return response

        elif command == "run_demo":
            # Start demo in background
            asyncio.create_task(run_demo())
            response["message"] = "Demo sequence started"
            last_successful_command_time = time.time()
            return response

        else:
            logger.warning(f"Unknown command: {command}")
            response["status"] = "error"
            response["message"] = f"Unknown command: {command}"
            return response

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        response["status"] = "error"
        response["message"] = f"Command error: {str(e)}"
        return response


async def run_demo():
    """Run a safe demo sequence that showcases the capabilities of the actuator."""
    global demo_running, axis, current_position

    if demo_running:
        logger.info("Demo already running")
        return

    demo_running = True
    logger.info("Starting demo sequence")

    try:
        if not RUNNING_ON_RPI or not axis:
            # Simulate demo in non-RPi mode
            positions = [-25, -15, -5, 5, 15, 25, 0]
            for pos in positions:
                if shutdown_requested:
                    break

                logger.info(f"Demo: Simulating move to {pos}mm")
                with position_lock:
                    # Simulate gradual movement
                    current_pos = current_position
                    steps = 20
                    for i in range(steps):
                        if shutdown_requested:
                            break
                        progress = (i + 1) / steps
                        current_position = current_pos + (pos - current_pos) * progress
                        await asyncio.sleep(0.1)
                await asyncio.sleep(1)
            logger.info("Demo sequence completed (simulation)")
        else:
            # Real hardware demo
            try:
                # First, set default parameters
                set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
                axis.setSpeed(DEFAULT_SPEED)

                # Demo positions with different speeds/acce/dece
                demo_positions = [
                    {"pos": -15, "speed": 500, "acce": 32750, "dece": 32750},
                    {"pos": 15, "speed": 1000, "acce": 65000, "dece": 65000},
                    {"pos": -20, "speed": 250, "acce": 16375, "dece": 16375},
                    {"pos": 20, "speed": 750, "acce": 48000, "dece": 48000},
                    {"pos": 0, "speed": DEFAULT_SPEED, "acce": DEFAULT_ACCELERATION, "dece": DEFAULT_DECELERATION}
                ]

                for step in demo_positions:
                    if shutdown_requested:
                        break

                    # Set parameters
                    set_acce_dece_params(step["acce"], step["dece"])
                    axis.setSpeed(step["speed"])
                    logger.info(
                        f"Demo: Moving to {step['pos']}mm (Speed={step['speed']}, ACCE={step['acce']}, DECE={step['dece']})"
                    )

                    # Move to position
                    axis.moveTo(step["pos"])

                    # Wait for move to complete (with timeout)
                    start_time = time.time()
                    while time.time() - start_time < 10:  # 10 second timeout
                        if shutdown_requested:
                            break

                        try:
                            # Check if we're at position
                            current_pos = axis.getPos()
                            with position_lock:
                                current_position = current_pos

                            # If close enough to target, move on
                            if abs(current_pos - step["pos"]) < 0.1:
                                break
                        except Exception as e:
                            logger.warning(f"Error reading position: {str(e)}")

                        await asyncio.sleep(0.1)

                    # Pause at each position
                    await asyncio.sleep(1)

                # Restore default parameters
                set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
                axis.setSpeed(DEFAULT_SPEED)
                logger.info("Demo sequence completed (hardware)")

            except Exception as e:
                logger.error(f"Error in demo sequence: {str(e)}")
                try:
                    # Try to stop any motion
                    axis.stopMove()
                except:
                    pass
    except Exception as e:
        logger.error(f"Unexpected error in demo sequence: {str(e)}")

    finally:
        demo_running = False


async def send_position_updates(websocket):
    """Send position updates at regular intervals."""
    global current_position
    
    logger.info("Starting position update sender task")
    
    while not shutdown_requested:
        try:
            # Get current position
            with position_lock:
                pos = current_position
                if RUNNING_ON_RPI and axis:
                    try:
                        pos = axis.getPos()
                        current_position = pos  # Update the shared position value
                    except Exception as e:
                        logger.error(f"Error getting position: {str(e)}")
            
            # Send position update
            message = {
                "type": "position_update",
                "rpiId": STATION_ID,
                "epos": pos
            }
            
            await websocket.send(json.dumps(message))
            
            # Sleep until next update
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error sending position update: {str(e)}")
            await asyncio.sleep(1)  # Error recovery delay


async def health_checker(websocket):
    """Monitor and report on system health."""
    global last_successful_command_time, last_successful_frame_time
    global last_ping_response_time
    
    logger.info("Starting health checker task")
    
    last_ping_time = time.time()
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            
            # Send ping messages for latency measurement
            if current_time - last_ping_time >= CONNECTION_HEARTBEAT_INTERVAL:
                ping_message = {
                    "type": "ping",
                    "rpiId": STATION_ID,
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    await websocket.send(json.dumps(ping_message))
                    logger.debug("Sent ping message for latency measurement")
                    last_ping_time = current_time
                except Exception as e:
                    logger.error(f"Error sending ping: {e}")
            
            # Check for issues
            if RUNNING_ON_RPI:
                # Check camera health
                if picam2 is None or not hasattr(picam2, 'started') or not picam2.started:
                    logger.warning("Health check: Camera not initialized")
                    initialize_camera()
                
                # Check controller health
                if controller is None or axis is None:
                    logger.warning("Health check: Controller not initialized")
                    initialize_xeryon_controller()
                
                # Check for thermal protection or amplifier errors
                if thermal_error_count > 0 or amplifier_error_count > 0:
                    logger.warning(
                        f"Health check: Detected errors - Thermal: {thermal_error_count}, Amplifier: {amplifier_error_count}"
                    )
                
                # Check for long-running frame transmission issues
                if current_time - last_successful_frame_time > 5:
                    logger.warning(
                        f"Health check: No frames sent for {current_time - last_successful_frame_time:.1f} seconds"
                    )
                
                # Check for command processing issues
                if current_time - last_successful_command_time > 60:
                    logger.warning(
                        f"Health check: No commands processed for {current_time - last_successful_command_time:.1f} seconds"
                    )
                
                # Check for ping response timeouts
                if current_time - last_ping_response_time > 15:
                    logger.warning(
                        f"Health check: No ping responses for {current_time - last_ping_response_time:.1f} seconds"
                    )
            
            # Sleep before next check
            await asyncio.sleep(5.0)
        
        except Exception as e:
            logger.error(f"Error in health checker: {e}")
            await asyncio.sleep(10.0)


async def flush_buffers():
    """Aggressively flush all buffers to prevent data buildup."""
    logger.info("Starting buffer flush task")
    
    while not shutdown_requested:
        try:
            if RUNNING_ON_RPI:
                # Flush serial port if needed
                if controller is not None:
                    flush_serial_port()
                
                # Flush camera frames if needed
                if picam2 is not None and hasattr(picam2, 'started') and picam2.started:
                    try:
                        # Capture and discard a frame
                        _ = picam2.capture_array("main")
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
            
            # Wait before next flush
            await asyncio.sleep(15.0)  # Flush every 15 seconds
        
        except Exception as e:
            logger.error(f"Error in buffer flush task: {e}")
            await asyncio.sleep(5.0)  # Error recovery delay


async def command_processor():
    """Process queued commands in the background."""
    logger.info("Starting command processor task")
    
    while not shutdown_requested:
        try:
            # Get command from queue with timeout
            try:
                command_data = await asyncio.wait_for(command_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No command in queue, continue
                continue
            
            # Process the command
            response = await process_command(command_data)
            
            # Send response if needed
            if command_data.get('_websocket') and command_data.get('_respond', True):
                if response:  # Some commands like pong don't need a response
                    try:
                        # Add response metadata
                        response['type'] = 'command_response'
                        response['command'] = command_data.get('command')
                        response['timestamp'] = datetime.now().isoformat()
                        
                        # Send response
                        await command_data['_websocket'].send(json.dumps(response))
                    except Exception as e:
                        logger.error(f"Error sending command response: {e}")
            
            # Mark command as complete
            command_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in command processor: {e}")
            await asyncio.sleep(1.0)


# ===== MAIN CLIENT =====
async def rpi_client():
    """Main client function with robust connection and error handling."""
    global last_ping_response_time, reconnect_delay, total_connection_failures
    global startup_time

    startup_time = time.time()
    logger.info(f"Starting Raspberry Pi client for {STATION_ID}")
    logger.info(f"Server URL: {SERVER_URL}")

    # Connection attempt tracking
    attempt = 0
    reconnect_delay = RECONNECT_BASE_DELAY

    while not shutdown_requested:
        try:
            attempt += 1
            logger.info(f"Connection attempt {attempt}/{MAX_RECONNECT_ATTEMPTS}")

            # Ultra-aggressive connection attempt with timeout
            try:
                websocket = await asyncio.wait_for(
                    websockets.connect(SERVER_URL),
                    timeout=MAX_CONNECTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(f"Connection timeout after {MAX_CONNECTION_TIMEOUT}s")
                total_connection_failures += 1

                # Exponential backoff with jitter
                reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
                jitter = random.uniform(0.8, 1.2)  # Add 20% jitter
                actual_delay = reconnect_delay * jitter
                
                logger.info(f"Waiting {actual_delay:.2f}s before next attempt")
                await asyncio.sleep(actual_delay)
                continue

            # Connection successful!
            logger.info("Connected to server successfully")
            reconnect_delay = RECONNECT_BASE_DELAY  # Reset delay on successful connection
            last_ping_response_time = time.time()  # Reset ping timer

            # Register with server
            logger.info("Sending registration message")
            await websocket.send(json.dumps({
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"  # Combined camera/control connection
            }))

            # Initialize hardware if on RPi
            if RUNNING_ON_RPI:
                initialize_camera()
                initialize_xeryon_controller()

            # Start background tasks
            frame_task = asyncio.create_task(send_camera_frames(websocket))
            pos_task = asyncio.create_task(send_position_updates(websocket))
            health_task = asyncio.create_task(health_checker(websocket))
            flush_task = asyncio.create_task(flush_buffers())
            cmd_task = asyncio.create_task(command_processor())
            
            # Heart of the client - process incoming messages
            try:
                async for message in websocket:
                    # Process received message
                    try:
                        data = json.loads(message)
                        message_type = data.get('type', '')
                        
                        # Route message based on type
                        if message_type == 'command':
                            # Add the websocket to the command data for response
                            data['_websocket'] = websocket
                            
                            # Queue the command for processing
                            await command_queue.put(data)
                        
                        elif message_type == 'ping':
                            # Handle ping request directly
                            response = await process_command(data)
                            if response:
                                await websocket.send(json.dumps(response))
                        
                        elif message_type == 'pong':
                            # Update the last ping response time
                            last_ping_response_time = time.time()
                            logger.debug("Received pong message")
                        
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON received: {message[:100]}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
            
            except ConnectionClosed:
                logger.warning("Connection closed by server")
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
            
            # Clean up tasks
            logger.info("Cleaning up background tasks")
            for task in [frame_task, pos_task, health_task, flush_task, cmd_task]:
                if not task.done():
                    task.cancel()
            
            try:
                await asyncio.wait_for(websocket.close(), timeout=MAX_CLOSE_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                pass
            
            logger.info("Connection closed, will reconnect shortly...")
            await asyncio.sleep(reconnect_delay)

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await asyncio.sleep(reconnect_delay)


# ===== MAIN ENTRY POINT =====
async def main():
    """Entry point with proper signal handling and cleanup."""
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for sig in signals:
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
    
    logger.info("=== Xeryon Bulletproof Client Starting ===")
    
    try:
        await rpi_client()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        await shutdown()


async def shutdown(sig=None):
    """Clean shutdown procedure."""
    global shutdown_requested
    
    if shutdown_requested:
        return
    
    shutdown_requested = True
    logger.info("Shutdown requested")
    
    # Stop hardware if on RPi
    if RUNNING_ON_RPI:
        # Stop controller first
        stop_controller()
        # Then stop camera
        stop_camera()
    
    logger.info("Shutdown complete")


# Run the client
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        sys.exit(1)