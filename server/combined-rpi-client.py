#!/usr/bin/env python3
"""
Bulletproof Raspberry Pi Client for Xeryon Demo Station
- Ultra-responsive with real-time performance
- Robust error handling and recovery
- Optimized for reliability and low latency
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
RESOLUTION_WIDTH = 1280  # 1280
RESOLUTION_HEIGHT = 720  # 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.2  # Reduced frequency to 200ms to reduce load
COMMAND_TIMEOUT = 2.0  # Timeout for serial commands (2 seconds)
COMMAND_RATE_LIMIT = 0.05  # Minimum interval between commands (50ms)

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.000001  # Reduced to 1μs for maximum responsiveness

# Connection parameters
MAX_RECONNECT_ATTEMPTS = 9999  # Effectively infinite retries
RECONNECT_BASE_DELAY = 0.5  # Start with 500ms delay
MAX_RECONNECT_DELAY = 5.0  # Cap at 5 seconds maximum
MAX_CONNECTION_TIMEOUT = 3.0  # Timeout for connection attempts
MAX_CLOSE_TIMEOUT = 1.0  # Timeout for connection closure
CONNECTION_HEARTBEAT_INTERVAL = 5.0  # Send heartbeats every 5 seconds
BUFFER_FLUSH_INTERVAL = 10.0  # Flush USB less frequently (10 seconds)

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

# Tracking variables
position_lock = threading.Lock()
serial_lock = threading.Lock()  # Synchronize serial access
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
jpeg_executor = ThreadPoolExecutor(max_workers=2)


# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port():
    """Aggressively flush serial port to avoid buffer issues."""
    if not RUNNING_ON_RPI:
        return True

    try:
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            try:
                subprocess.run(["usbreset", COM_PORT], check=False)
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to reset USB: {str(e)}")

            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available after reset")
                return False

        with serial.Serial(COM_PORT, 115200, timeout=0.5) as ser:
            for _ in range(2):  # Reduced flushes to minimize interference
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.01)

            ser.write(b'\r\n')
            time.sleep(0.05)
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

        with serial_lock:
            if not flush_serial_port():
                logger.error(
                    "Failed to flush serial port - aborting controller init")
                return False

        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        time.sleep(0.5)

        axis.setUnits(Units.mm)
        time.sleep(0.1)
        axis.sendCommand("POLI=50")
        time.sleep(0.1)

        thermal_error_count = 0
        amplifier_error_count = 0
        serial_error_count = 0

        axis.setSpeed(DEFAULT_SPEED)
        time.sleep(0.1)
        set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
        time.sleep(0.1)

        axis.sendCommand("ENBL=1")
        time.sleep(0.1)

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


# ===== CAMERA MANAGEMENT =====
def initialize_camera():
    """Initialize camera with robust error handling."""
    global picam2

    CROP_FRACTION = 1 / 3
    HORIZONTAL_SHIFT = 0.0
    VERTICAL_SHIFT = 0.0
    SENSOR_WIDTH = 4608
    SENSOR_HEIGHT = 2592

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True

    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()

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

        config = picam2.create_video_configuration(
            main={
                "size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT),
                "format": "RGB888"
            },
            controls={"ScalerCrop": scaler_crop})

        picam2.configure(config)
        picam2.start()
        picam2.set_controls({
            "AeEnable": False,
            "AfMode": 2,
            "ExposureTime": 20000,
            "AnalogueGain": 1.0
        })
        time.sleep(5)

        for i in range(3):
            _ = picam2.capture_array("main")
            time.sleep(0.1)

        logger.info(
            f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        return True

    except Exception as e:
        logger.error(f"Camera initialization failed: {str(e)}")
        stop_camera()
        return False


async def encode_jpeg_async(frame, quality):
    return await asyncio.to_thread(encode_jpeg, frame, quality)


def encode_jpeg(frame, quality):
    encode_param = [
        cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1,
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


# ===== COMMAND PROCESSING =====
async def process_command(data):
    """Process incoming commands with comprehensive error handling and safety checks."""
    global axis, last_successful_command_time, current_position, last_command_time
    global thermal_error_count, amplifier_error_count

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

        # Check controller state before sending commands
        with serial_lock:
            try:
                stat = await asyncio.to_thread(axis.getData, "STAT")
                if axis.isThermalProtection1(
                        stat) or axis.isThermalProtection2(stat):
                    logger.error("Controller in thermal protection state")
                    response["status"] = "error"
                    response[
                        "message"] = "Controller in thermal protection state"
                    return response
                if axis.isErrorLimit(stat):
                    logger.error("Controller in error limit state")
                    response["status"] = "error"
                    response["message"] = "Controller in error limit state"
                    return response
                if axis.isSafetyTimeoutTriggered(stat):
                    logger.error("Controller safety timeout triggered")
                    response["status"] = "error"
                    response["message"] = "Controller safety timeout triggered"
                    return response

                axis.sendCommand("ENBL=1")
            except Exception as e:
                logger.warning(f"Error checking controller state: {str(e)}")
                response["status"] = "error"
                response[
                    "message"] = f"Error checking controller state: {str(e)}"
                return response

        # Handle acceleration and deceleration commands
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(
                    direction) if direction.isdigit() else DEFAULT_ACCELERATION
            with serial_lock:
                set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            last_successful_command_time = time.time()
            return response

        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(
                    direction) if direction.isdigit() else DEFAULT_DECELERATION
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
            if step_size is None or not isinstance(
                    step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "μm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")

            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
            final_step = step_value if direction == "right" else -step_value

            try:
                with serial_lock:
                    try:
                        await asyncio.wait_for(asyncio.to_thread(
                            axis.step, final_step),
                                               timeout=COMMAND_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.error("Timeout waiting for axis.step")
                        raise Exception("Timeout waiting for axis.step")

                with position_lock:
                    current_position += final_step

                with serial_lock:
                    try:
                        epos = await asyncio.wait_for(asyncio.to_thread(
                            axis.getEPOS),
                                                      timeout=COMMAND_TIMEOUT)
                    except asyncio.TimeoutError:
                        logger.error("Timeout waiting for axis.getEPOS")
                        raise Exception("Timeout waiting for axis.getEPOS")

                response[
                    "message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
                response["step_executed_mm"] = final_step
                response["epos_mm"] = epos
                logger.info(
                    f"Move executed: {final_step:.6f} mm to position: {epos:.6f} mm"
                )
                last_successful_command_time = time.time()
            except Exception as e:
                error_str = str(e)
                if "amplifier error" in error_str:
                    amplifier_error_count += 1
                elif "thermal protection" in error_str:
                    thermal_error_count += 1
                raise

        elif command == "home":
            with serial_lock:
                await asyncio.wait_for(asyncio.to_thread(axis.findIndex),
                                       timeout=COMMAND_TIMEOUT)
                epos = await asyncio.wait_for(asyncio.to_thread(axis.getEPOS),
                                              timeout=COMMAND_TIMEOUT)

            with position_lock:
                current_position = epos

            response["message"] = f"Homed to index, EPOS {epos:.6f} mm"
            response["epos_mm"] = epos
            logger.info(f"Homed to index, EPOS: {epos:.6f} mm")
            last_successful_command_time = time.time()

        elif command == "speed":
            speed_value = float(direction)
            speed_value = max(1, min(1000, speed_value))
            with serial_lock:
                await asyncio.wait_for(asyncio.to_thread(
                    axis.setSpeed, speed_value),
                                       timeout=COMMAND_TIMEOUT)
            response["message"] = f"Speed set to {speed_value:.2f} mm/s"
            logger.info(f"Speed set to {speed_value:.2f} mm/s")
            last_successful_command_time = time.time()

        elif command == "scan":
            if direction == "right":
                with serial_lock:
                    await asyncio.wait_for(asyncio.to_thread(
                        axis.startScan, 1),
                                           timeout=COMMAND_TIMEOUT)
                response["message"] = "Scanning right"
            elif direction == "left":
                with serial_lock:
                    await asyncio.wait_for(asyncio.to_thread(
                        axis.startScan, -1),
                                           timeout=COMMAND_TIMEOUT)
                response["message"] = "Scanning left"
            else:
                raise ValueError(f"Invalid scan direction: {direction}")

            logger.info(f"Scan started: {direction}")
            last_successful_command_time = time.time()

        elif command == "demo_start":
            global demo_running
            if not demo_running:
                demo_running = True
                asyncio.create_task(run_demo())
                response["message"] = "Demo started"
                logger.info("Demo started")
            else:
                response["message"] = "Demo already running"
                logger.info("Demo already running - request ignored")
            last_successful_command_time = time.time()

        elif command == "demo_stop":
            if demo_running:
                demo_running = False
                with serial_lock:
                    await asyncio.wait_for(asyncio.to_thread(axis.stopScan),
                                           timeout=COMMAND_TIMEOUT)
                    await asyncio.wait_for(asyncio.to_thread(axis.setDPOS, 0),
                                           timeout=COMMAND_TIMEOUT)

                with position_lock:
                    current_position = 0

                response["message"] = "Demo stopped, DPOS 0 mm"
                logger.info("Demo stopped, position reset to 0 mm")
            else:
                response["message"] = "No demo running"
                logger.info("No demo to stop - request ignored")
            last_successful_command_time = time.time()

        elif command == "stop":
            with serial_lock:
                await asyncio.wait_for(asyncio.to_thread(axis.stopScan),
                                       timeout=COMMAND_TIMEOUT)
                await asyncio.wait_for(asyncio.to_thread(axis.setDPOS, 0),
                                       timeout=COMMAND_TIMEOUT)

            with position_lock:
                current_position = 0

            response["message"] = "Stopped, DPOS 0 mm"
            logger.info("Stopped, position reset to 0 mm")
            last_successful_command_time = time.time()

        elif command == "reset_params":
            with serial_lock:
                await asyncio.wait_for(asyncio.to_thread(
                    axis.setSpeed, DEFAULT_SPEED),
                                       timeout=COMMAND_TIMEOUT)
                set_acce_dece_params(DEFAULT_ACCELERATION,
                                     DEFAULT_DECELERATION)
            response["message"] = "Parameters reset to defaults"
            response["speed"] = DEFAULT_SPEED
            response["acceleration"] = DEFAULT_ACCELERATION
            response["deceleration"] = DEFAULT_DECELERATION
            logger.info("Parameters reset to defaults")
            last_successful_command_time = time.time()

        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        global last_error_time
        last_error_time = time.time()

        response["status"] = "error"
        response["message"] = f"Command '{command}' failed: {str(e)}"
        logger.error(f"Command error ({command}): {str(e)}")

        if RUNNING_ON_RPI and axis:
            with serial_lock:
                try:
                    axis.sendCommand("ENBL=1")
                    time.sleep(0.1)
                except Exception as recovery_error:
                    logger.error(
                        f"Error recovery failed: {str(recovery_error)}")

    return response


async def run_demo():
    """Run a safe demo sequence that showcases the capabilities of the actuator."""
    global demo_running, axis, current_position, last_command_time

    logger.info("Demo started")
    try:
        if not axis:
            logger.error("Cannot run demo - no axis initialized")
            demo_running = False
            return

        demo_running = True

        with serial_lock:
            await asyncio.wait_for(asyncio.to_thread(axis.setDPOS, 0),
                                   timeout=COMMAND_TIMEOUT)
        with position_lock:
            current_position = 0
        logger.info("Demo: Position reset to 0 mm")
        await asyncio.sleep(1)

        for i in range(100):
            if not demo_running or not axis:
                break

            try:
                speed = random.uniform(10, 500)
                with serial_lock:
                    await asyncio.wait_for(asyncio.to_thread(
                        axis.setSpeed, speed),
                                           timeout=COMMAND_TIMEOUT)
                logger.info(f"Demo: Speed set to {speed:.1f} mm/s")

                action = random.choice(["step", "scan"])

                if action == "step":
                    direction = random.choice([1, -1])
                    step_size = random.uniform(0.1, 2.0)

                    with serial_lock:
                        await asyncio.wait_for(asyncio.to_thread(
                            axis.step, step_size * direction),
                                               timeout=COMMAND_TIMEOUT)

                    with position_lock:
                        current_position += step_size * direction

                    logger.info(
                        f"Demo: Step {step_size:.2f} mm {'right' if direction == 1 else 'left'}"
                    )
                    await asyncio.sleep(random.uniform(0.3, 1.0))

                else:
                    direction = random.choice([1, -1])
                    with serial_lock:
                        await asyncio.wait_for(asyncio.to_thread(
                            axis.startScan, direction),
                                               timeout=COMMAND_TIMEOUT)
                    logger.info(
                        f"Demo: Scan {'right' if direction == 1 else 'left'}")

                    scan_time = random.uniform(0.3, 1.5)
                    await asyncio.sleep(scan_time)

                    with serial_lock:
                        await asyncio.wait_for(asyncio.to_thread(
                            axis.stopScan),
                                               timeout=COMMAND_TIMEOUT)
                    logger.info("Demo: Scan stopped")

                    try:
                        with serial_lock:
                            epos = await asyncio.wait_for(
                                asyncio.to_thread(axis.getEPOS),
                                timeout=COMMAND_TIMEOUT)
                        with position_lock:
                            current_position = epos
                    except Exception as e:
                        logger.error(f"Demo position update error: {str(e)}")

                await asyncio.sleep(random.uniform(0.2, 0.8))

            except Exception as e:
                logger.error(f"Demo error: {str(e)}")
                with serial_lock:
                    try:
                        if axis:
                            axis.stopScan()
                            axis.sendCommand("ENBL=1")
                    except:
                        pass
                await asyncio.sleep(1)

        logger.info("Demo sequence completed")
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        demo_running = False
        try:
            with serial_lock:
                if axis:
                    await asyncio.wait_for(asyncio.to_thread(axis.stopScan),
                                           timeout=COMMAND_TIMEOUT)
                    await asyncio.wait_for(asyncio.to_thread(axis.setDPOS, 0),
                                           timeout=COMMAND_TIMEOUT)
            with position_lock:
                current_position = 0
        except Exception as e:
            logger.error(f"Demo cleanup error: {str(e)}")


# ===== BACKGROUND TASKS =====
async def send_camera_frames(websocket):
    """Send the newest camera frames in real-time, dropping older frames if necessary."""
    global picam2, last_successful_frame_time

    frame_count = 0
    last_frame_time = time.time()

    logger.info("Starting camera frame sender task")

    while not shutdown_requested:
        try:
            if not RUNNING_ON_RPI:
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

            # Always capture the newest frame, dropping any pending frames
            try:
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue

            last_frame_time = time.time()
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # Add frame info overlay
            id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
            cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)

            # Encode with highest priority
            try:
                buffer = await encode_jpeg_async(frame, JPEG_QUALITY)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Frame encoding error: {e}")
                await asyncio.sleep(0.01)
                continue

            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": jpg_as_text,
                "timestamp": frame_time,
                "frameNumber": frame_count
            }

            try:
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_successful_frame_time = time.time()

                if frame_count % 30 == 0:
                    logger.debug(f"Sent frame {frame_count} at {frame_time}")

            except Exception as e:
                logger.error(f"Frame send error: {e}")
                await asyncio.sleep(0.01)

            # Target FPS control with minimal delay
            elapsed = time.time() - last_frame_time
            frame_interval = 1.0 / TARGET_FPS
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)

        except Exception as e:
            logger.error(f"Camera frame sender error: {str(e)}")
            await asyncio.sleep(0.1)


async def send_position_updates(websocket):
    """Send position updates at regular intervals."""
    global axis, last_successful_command_time, current_position

    last_epos = None
    last_update_time = time.time()

    logger.info("Starting position update sender task")

    while not shutdown_requested:
        try:
            if not RUNNING_ON_RPI or not axis:
                if RUNNING_ON_RPI:
                    logger.warning(
                        "Axis not initialized - pausing position updates")
                await asyncio.sleep(1)
                continue

            current_time = time.time()
            elapsed = current_time - last_update_time

            if elapsed < EPOS_UPDATE_INTERVAL:
                await asyncio.sleep(EPOS_UPDATE_INTERVAL - elapsed)

            last_update_time = time.time()

            try:
                with serial_lock:
                    epos = await asyncio.wait_for(asyncio.to_thread(
                        axis.getEPOS),
                                                  timeout=COMMAND_TIMEOUT)

                with position_lock:
                    current_position = epos

                if last_epos != epos or elapsed > 1.0:
                    position_data = {
                        "type": "position_update",
                        "rpiId": STATION_ID,
                        "epos": epos,
                        "timestamp": datetime.now().isoformat()
                    }

                    try:
                        await websocket.send(json.dumps(position_data))
                        last_epos = epos
                        last_successful_command_time = time.time()
                        logger.debug(f"Position update: {epos:.6f} mm")
                    except Exception as e:
                        logger.error(f"Position update send error: {e}")
                        await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Position reading error: {e}")
                await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            await asyncio.sleep(0.5)


async def health_checker(websocket):
    """Monitor and report on system health."""
    global startup_time, thermal_error_count, amplifier_error_count, serial_error_count
    health_check_interval = CONNECTION_HEARTBEAT_INTERVAL

    logger.info(
        f"Starting health monitor task with {health_check_interval}s heartbeat interval"
    )

    while not shutdown_requested:
        try:
            current_time = time.time()
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            ping_silence = current_time - last_ping_response_time
            uptime = current_time - startup_time

            if int(uptime) % 60 == 0:
                logger.info(
                    f"Health status: Uptime={uptime:.1f}s, Errors: Thermal={thermal_error_count}, "
                    f"Amplifier={amplifier_error_count}, Serial={serial_error_count}"
                )

            logger.debug(
                f"Health: command={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s"
            )

            if not hasattr(websocket, 'open') or not websocket.open:
                logger.error(
                    "WebSocket reported as closed - triggering reconnection")
                break

            health_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID,
                "uptime": uptime,
                "errors": {
                    "thermal": thermal_error_count,
                    "amplifier": amplifier_error_count,
                    "serial": serial_error_count
                },
                "silence": {
                    "command": command_silence,
                    "frame": frame_silence,
                    "ping": ping_silence
                },
                "client_version": "2.2-ultra-reliable"
            }

            try:
                await asyncio.wait_for(websocket.send(json.dumps(health_data)),
                                       timeout=2.0)
            except asyncio.TimeoutError:
                logger.error(
                    "Health update send timed out - triggering reconnection")
                break

            if command_silence > 30 * 60:
                logger.warning(
                    f"Long command silence detected: {command_silence:.1f}s")

            if frame_silence > 30:
                logger.warning(f"Frame silence detected: {frame_silence:.1f}s")
                if RUNNING_ON_RPI and picam2:
                    logger.info("Attempting to reset camera due to silence")
                    try:
                        stop_camera()
                        await asyncio.sleep(1)
                        initialize_camera()
                    except Exception as e:
                        logger.error(f"Failed to reset camera: {str(e)}")

            if not shutdown_requested:
                try:
                    ping_data = {
                        "type": "ping",
                        "timestamp": datetime.now().isoformat(),
                        "rpiId": STATION_ID,
                        "uptime": uptime
                    }
                    await asyncio.wait_for(websocket.send(
                        json.dumps(ping_data)),
                                           timeout=1.0)
                except Exception as e:
                    logger.error(f"Error sending ping: {str(e)}")
                    break

            await asyncio.sleep(health_check_interval)

        except asyncio.CancelledError:
            logger.info("Health monitor task cancelled")
            break
        except Exception as e:
            logger.error(f"Health checker error: {str(e)}")
            await asyncio.sleep(0.5)


async def flush_buffers():
    """Flush buffers to prevent data buildup, but only when necessary."""
    logger.info("Starting buffer flush task")

    while not shutdown_requested:
        try:
            # Only flush if there has been recent activity
            if (time.time() - last_successful_command_time) < 30:
                if RUNNING_ON_RPI and picam2 and hasattr(
                        picam2, 'started') and picam2.started:
                    try:
                        for _ in range(2):
                            _ = picam2.capture_array("main")
                        logger.debug("Camera buffers flushed")
                    except Exception as e:
                        logger.error(f"Camera buffer flush error: {e}")

                if RUNNING_ON_RPI and os.path.exists(COM_PORT):
                    with serial_lock:
                        try:
                            flush_serial_port()
                        except Exception as e:
                            logger.error(f"Serial buffer flush error: {e}")

            gc.collect()
            await asyncio.sleep(BUFFER_FLUSH_INTERVAL)

        except Exception as e:
            logger.error(f"Buffer flush error: {str(e)}")
            await asyncio.sleep(1)


async def command_processor():
    """Process queued commands in the background."""
    global shutdown_requested

    logger.info("Starting command processor task")

    while not shutdown_requested:
        try:
            await asyncio.sleep(MIN_SLEEP_DELAY)

            try:
                command = await asyncio.wait_for(command_queue.get(),
                                                 timeout=0.5)
            except asyncio.TimeoutError:
                continue

            websocket = getattr(command_processor, 'websocket', None)
            if websocket:
                try:
                    await websocket.send(json.dumps(command))
                    logger.debug(
                        f"Sent queued command: {command.get('type', 'unknown')} {command.get('command', '')}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send queued command: {str(e)}")
                    if command.get('status') == 'success':
                        await command_queue.put(command)

            await asyncio.sleep(0.05)

        except Exception as e:
            logger.error(f"Command processor error: {str(e)}")
            await asyncio.sleep(0.5)


# ===== MAIN CLIENT FUNCTION =====
async def rpi_client():
    """Main client function with robust connection and error handling."""
    global shutdown_requested, reconnect_delay, total_connection_failures
    global startup_time, demo_running

    startup_time = time.time()
    logger.info(f"Starting RPi Client version 2.2 for {STATION_ID}")
    logger.info(f"Connecting to server: {SERVER_URL}")

    if RUNNING_ON_RPI:
        logger.info("Initializing camera...")
        camera_initialized = initialize_camera()
        if not camera_initialized:
            logger.warning("First camera init failed, retrying...")
            await asyncio.sleep(2)
            camera_initialized = initialize_camera()

        logger.info("Initializing Xeryon controller...")
        controller_initialized = initialize_xeryon_controller()
        if not controller_initialized:
            logger.warning("First controller init failed, retrying...")
            await asyncio.sleep(2)
            controller_initialized = initialize_xeryon_controller()

    connection_id = f"bp_{int(time.time())}"

    buffer_task = asyncio.create_task(flush_buffers())
    cmd_processor_task = asyncio.create_task(command_processor())

    while not shutdown_requested:
        try:
            logger.info(
                f"Connecting to {SERVER_URL} (attempt {total_connection_failures + 1})..."
            )

            try:
                websocket = await asyncio.wait_for(
                    websockets.connect(
                        SERVER_URL,
                        ping_interval=None,
                        ping_timeout=None,
                        close_timeout=MAX_CLOSE_TIMEOUT,
                        max_size=10_000_000,
                        compression=None,
                    ),
                    timeout=MAX_CONNECTION_TIMEOUT)
                logger.info("WebSocket connection established successfully")
            except asyncio.TimeoutError:
                logger.error(
                    f"Connection timeout after {MAX_CONNECTION_TIMEOUT}s - will retry immediately"
                )
                continue
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                raise

            logger.info("WebSocket connection established")

            registration_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined",
                "status": "ready",
                "message":
                f"RPi {STATION_ID} combined connection initialized (Bulletproof v2.2)",
                "connectionId": connection_id,
                "timestamp": datetime.now().isoformat()
            }

            await websocket.send(json.dumps(registration_message))
            logger.info(f"Sent registration message for {STATION_ID}")

            command_processor.websocket = websocket

            frame_task = asyncio.create_task(send_camera_frames(websocket))
            position_task = asyncio.create_task(
                send_position_updates(websocket))
            health_task = asyncio.create_task(health_checker(websocket))

            total_connection_failures = 0
            reconnect_delay = RECONNECT_BASE_DELAY

            try:
                while not shutdown_requested:
                    try:
                        message = await asyncio.wait_for(websocket.recv(),
                                                         timeout=30)
                    except asyncio.TimeoutError:
                        logger.warning(
                            "No messages received for 30s - checking connection..."
                        )
                        try:
                            ping_data = {
                                "type": "ping",
                                "timestamp": datetime.now().isoformat(),
                                "rpiId": STATION_ID
                            }
                            await websocket.send(json.dumps(ping_data))
                            logger.debug(
                                "Ping sent successfully - connection still active"
                            )
                            continue
                        except Exception:
                            logger.error(
                                "Connection seems dead - will reconnect")
                            break

                    try:
                        data = json.loads(message)

                        if data.get("type") == "command":
                            response = await process_command(data)
                            if response:
                                await command_queue.put(response)

                        elif data.get("type") == "ping":
                            response = {
                                "type": "pong",
                                "timestamp": data.get("timestamp"),
                                "rpiId": STATION_ID
                            }
                            await websocket.send(json.dumps(response))
                            logger.debug(
                                f"Replied to ping: {data.get('timestamp')}")

                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON received: {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {str(e)}")
                        await asyncio.sleep(0.1)

            except websockets.exceptions.ConnectionClosed as e:
                logger.error(f"WebSocket connection closed: {e}")

            for task in [frame_task, position_task, health_task]:
                if not task.done():
                    task.cancel()

            try:
                await asyncio.gather(frame_task,
                                     position_task,
                                     health_task,
                                     return_exceptions=True)
            except asyncio.CancelledError:
                pass

            logger.info("Background tasks stopped, will reconnect")
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")

            total_connection_failures += 1
            if "device not connected" in str(
                    e).lower() or "cannot connect" in str(e).lower():
                actual_delay = 0.1
                logger.warning(
                    f"Connection refused - retrying in {actual_delay:.1f}s")
            else:
                reconnect_delay = min(
                    MAX_RECONNECT_DELAY,
                    RECONNECT_BASE_DELAY *
                    (1.2**min(total_connection_failures % 5, 4)))
                jitter = random.uniform(0, 0.1 * reconnect_delay)
                actual_delay = reconnect_delay + jitter

            logger.info(
                f"Retrying connection in {actual_delay:.2f}s (attempt {total_connection_failures})..."
            )
            if total_connection_failures < 3:
                actual_delay = min(0.1, actual_delay)
                logger.info(
                    f"First few attempts - using ultra-fast retry ({actual_delay:.2f}s)"
                )

            await asyncio.sleep(actual_delay)

            if total_connection_failures % 3 == 0:
                logger.warning(
                    f"Multiple connection failures ({total_connection_failures}), resetting hardware..."
                )

                if RUNNING_ON_RPI:
                    stop_camera()
                    stop_controller()

                demo_running = False
                await asyncio.sleep(3)

                if RUNNING_ON_RPI:
                    initialize_camera()
                    initialize_xeryon_controller()


# ===== ENTRY POINT =====
async def main():
    """Entry point with proper signal handling and cleanup."""
    global shutdown_requested

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        await rpi_client()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        await shutdown()


async def shutdown():
    """Clean shutdown procedure."""
    global shutdown_requested

    if shutdown_requested:
        return

    shutdown_requested = True
    logger.info("Shutting down...")

    if RUNNING_ON_RPI:
        stop_camera()
        stop_controller()

    gc.collect()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        if RUNNING_ON_RPI:
            try:
                if 'picam2' in globals() and picam2:
                    stop_camera()
                if 'controller' in globals() and controller:
                    stop_controller()
            except:
                pass
