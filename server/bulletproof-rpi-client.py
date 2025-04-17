#!/usr/bin/env python3
"""
Bulletproof Raspberry Pi Client for Xeryon Demo Station
- Ultra-responsive with real-time performance
- Robust error handling and recovery
- Optimized for reliability and low latency
- Aggressive buffer management to prevent hanging
- Dynamic FPS: 1 FPS after 30s of no movement, 25 FPS on movement
- Serial port flushed every 3 seconds
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
import gc
import subprocess
from datetime import datetime
from collections import deque
import threading
import signal
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor

# Will be imported on the actual RPi
try:
    from picamera2 import Picamera2
    from websockets.exceptions import ConnectionClosed
    import serial
    from turbojpeg import TurboJPEG
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
    jpeg = TurboJPEG()
except ImportError:
    RUNNING_ON_RPI = False
    jpeg = None

    class ConnectionClosed(Exception):
        pass

    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 50
TARGET_FPS = 25
LOW_FPS = 1
MOVEMENT_TIMEOUT = 30.0  # Seconds before dropping to LOW_FPS
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1
COMMAND_TIMEOUT = 60
MIN_SLEEP_DELAY = 0.000001
CONNECTION_HEARTBEAT_INTERVAL = 10.0
BUFFER_FLUSH_INTERVAL = 3.0  # Adjusted to 3 seconds for regular serial flushing

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500

# Connection parameters
MAX_RECONNECT_ATTEMPTS = 9999
RECONNECT_BASE_DELAY = 0.5
MAX_RECONNECT_DELAY = 5.0
MAX_CONNECTION_TIMEOUT = 3.0
MAX_CLOSE_TIMEOUT = 1.0

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
last_movement_time = time.time()  # Track last movement command
current_fps = TARGET_FPS  # Dynamic FPS
startup_time = None

# Tracking variables
position_lock = threading.Lock()
current_position = 0.0
thermal_error_count = 0
amplifier_error_count = 0
serial_error_count = 0
last_error_time = 0

# Connection state
total_connection_failures = 0
reconnect_delay = RECONNECT_BASE_DELAY

# Latency tracking
latency_log = deque(maxlen=100)

# ===== LOGGING SETUP =====
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(),
                        logging.FileHandler('/tmp/xeryon_client.log')
                        if RUNNING_ON_RPI else logging.NullHandler()
                    ])
logger = logging.getLogger("XeryonClient")
jpeg_executor = ThreadPoolExecutor(max_workers=4)


# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port():
    if not RUNNING_ON_RPI:
        return True

    try:
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            subprocess.run(["usbreset", COM_PORT], check=False)
            time.sleep(1)
            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available")
                return False

        with serial.Serial(COM_PORT, 115200, timeout=0.5) as ser:
            for _ in range(3):
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.01)
            ser.write(b'\r\n')
            time.sleep(0.05)
            _ = ser.read(ser.in_waiting or 1)
        logger.debug(f"Serial port {COM_PORT} flushed")
        return True
    except Exception as e:
        logger.error(f"Serial flush error: {e}")
        global serial_error_count
        serial_error_count += 1
        return False


def initialize_xeryon_controller():
    global controller, axis, thermal_error_count, amplifier_error_count, serial_error_count
    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking controller")
        return True

    try:
        logger.info(f"Initializing controller on {COM_PORT}")
        if not flush_serial_port():
            logger.error("Serial flush failed")
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
        logger.info("Controller initialized")
        return True
    except Exception as e:
        logger.error(f"Controller init failed: {e}")
        stop_controller()
        return False


def stop_controller():
    global controller, axis
    if not RUNNING_ON_RPI:
        return

    try:
        if controller and axis:
            axis.stopScan()
            time.sleep(0.1)
            controller.stop()
            logger.info("Controller stopped")
    except Exception as e:
        logger.error(f"Stop controller error: {e}")
    finally:
        controller = None
        axis = None
        gc.collect()


def set_acce_dece_params(acce_value=None, dece_value=None):
    global axis
    if not RUNNING_ON_RPI or not axis:
        return False

    try:
        if acce_value is not None:
            acce_value = max(0, min(65500, int(acce_value)))
            axis.sendCommand(f"ACCE={acce_value}")
            logger.info(f"Acceleration set to {acce_value}")
        if dece_value is not None:
            dece_value = max(0, min(65500, int(dece_value)))
            axis.sendCommand(f"DECE={dece_value}")
            logger.info(f"Deceleration set to {dece_value}")
        axis.sendCommand("ENBL=1")
        return True
    except Exception as e:
        logger.error(f"Set acce/dece error: {e}")
        return False


# ===== CAMERA MANAGEMENT =====
def initialize_camera():
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

        for _ in range(3):
            _ = picam2.capture_array("main")
            time.sleep(0.1)
        logger.info(
            f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        return True
    except Exception as e:
        logger.error(f"Camera init failed: {e}")
        stop_camera()
        return False


async def encode_jpeg_async(frame, quality):
    loop = asyncio.get_running_loop()
    if jpeg and RUNNING_ON_RPI:
        return await loop.run_in_executor(
            jpeg_executor, lambda: jpeg.encode(frame, quality=quality))
    else:
        encode_param = [
            cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_OPTIMIZE, 1
        ]
        return await loop.run_in_executor(
            jpeg_executor,
            lambda: cv2.imencode('.jpg', frame, encode_param)[1].tobytes())


def stop_camera():
    global picam2
    if not RUNNING_ON_RPI:
        return

    try:
        if picam2 and hasattr(picam2, 'started') and picam2.started:
            picam2.stop()
            picam2.close()
            logger.info("Camera stopped")
    except Exception as e:
        logger.error(f"Stop camera error: {e}")
    finally:
        picam2 = None
        gc.collect()


# ===== COMMAND PROCESSING =====
async def process_command(data):
    global axis, last_successful_command_time, last_movement_time, current_position, thermal_error_count, amplifier_error_count
    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))

    logger.debug(
        f"Command: {command}, dir: {direction}, step: {step_size}, unit: {step_unit}"
    )
    response = {"status": "success", "rpiId": STATION_ID}

    try:
        if message_type == "ping":
            response.update({
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            })
            return response
        elif message_type == "pong":
            global last_ping_response_time
            last_ping_response_time = time.time()
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
                response["status"] = "error"
                response["message"] = "Controller not initialized"
                return response
            response["message"] = f"Simulation: Executed {command}"
            last_successful_command_time = time.time()
            return response

        if axis:
            await asyncio.to_thread(axis.sendCommand, "ENBL=1")

        if command in ["acceleration", "acce"]:
            acce_value = int(
                direction) if direction.isdigit() else DEFAULT_ACCELERATION
            set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            last_successful_command_time = time.time()
            return response
        elif command in ["deceleration", "dece"]:
            dece_value = int(
                direction) if direction.isdigit() else DEFAULT_DECELERATION
            set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            last_successful_command_time = time.time()
            return response

        if acce_value is not None or dece_value is not None:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        if command in ["move", "step"]:
            if direction not in ["right", "left"]:
                raise ValueError(f"Invalid direction: {direction}")
            if not isinstance(step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "μm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")

            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
            final_step = step_value if direction == "right" else -step_value

            await asyncio.to_thread(axis.step, final_step)
            with position_lock:
                current_position += final_step
            epos = await asyncio.to_thread(axis.getEPOS)

            response[
                "message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
            response["step_executed_mm"] = final_step
            response["epos_mm"] = epos
            last_successful_command_time = time.time()
            last_movement_time = time.time()  # Update on movement command
            logger.info("Movement command received, setting FPS to 25")

        elif command == "home":
            await asyncio.to_thread(axis.findIndex)
            epos = await asyncio.to_thread(axis.getEPOS)
            with position_lock:
                current_position = epos
            response["message"] = f"Homed to index, EPOS {epos:.6f} mm"
            response["epos_mm"] = epos
            last_successful_command_time = time.time()

        elif command == "speed":
            speed_value = max(1, min(1000, float(direction)))
            await asyncio.to_thread(axis.setSpeed, speed_value)
            response["message"] = f"Speed set to {speed_value:.2f} mm/s"
            last_successful_command_time = time.time()

        elif command == "scan":
            if direction == "right":
                await asyncio.to_thread(axis.startScan, 1)
                response["message"] = "Scanning right"
            elif direction == "left":
                await asyncio.to_thread(axis.startScan, -1)
                response["message"] = "Scanning left"
            else:
                raise ValueError(f"Invalid scan direction: {direction}")
            last_successful_command_time = time.time()

        elif command == "demo_start":
            global demo_running
            if not demo_running:
                demo_running = True
                asyncio.create_task(run_demo())
                response["message"] = "Demo started"
            else:
                response["message"] = "Demo already running"
            last_successful_command_time = time.time()

        elif command == "demo_stop":
            if demo_running:
                demo_running = False
                await asyncio.to_thread(axis.stopScan)
                await asyncio.to_thread(axis.setDPOS, 0)
                with position_lock:
                    current_position = 0
                response["message"] = "Demo stopped, DPOS 0 mm"
            else:
                response["message"] = "No demo running"
            last_successful_command_time = time.time()

        elif command == "stop":
            await asyncio.to_thread(axis.stopScan)
            await asyncio.to_thread(axis.setDPOS, 0)
            with position_lock:
                current_position = 0
            response["message"] = "Stopped, DPOS 0 mm"
            last_successful_command_time = time.time()

        elif command == "reset_params":
            await asyncio.to_thread(axis.setSpeed, DEFAULT_SPEED)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            response["message"] = "Parameters reset to defaults"
            response["speed"] = DEFAULT_SPEED
            response["acceleration"] = DEFAULT_ACCELERATION
            response["deceleration"] = DEFAULT_DECELERATION
            last_successful_command_time = time.time()

        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        global last_error_time
        last_error_time = time.time()
        response["status"] = "error"
        response["message"] = f"Command '{command}' failed: {e}"
        logger.error(f"Command error: {e}")
        if RUNNING_ON_RPI and axis:
            await asyncio.to_thread(axis.sendCommand, "ENBL=1")

    return response


async def run_demo():
    global demo_running, axis, current_position
    logger.info("Demo started")
    try:
        if not axis:
            logger.error("No axis for demo")
            demo_running = False
            return

        demo_running = True
        await asyncio.to_thread(axis.setDPOS, 0)
        with position_lock:
            current_position = 0
        await asyncio.sleep(1)

        for _ in range(100):
            if not demo_running or not axis:
                break
            speed = random.uniform(10, 500)
            await asyncio.to_thread(axis.setSpeed, speed)
            action = random.choice(["step", "scan"])

            if action == "step":
                direction = random.choice([1, -1])
                step_size = random.uniform(0.1, 2.0)
                await asyncio.to_thread(axis.step, step_size * direction)
                with position_lock:
                    current_position += step_size * direction
                await asyncio.sleep(random.uniform(0.3, 1.0))
            else:
                direction = random.choice([1, -1])
                await asyncio.to_thread(axis.startScan, direction)
                await asyncio.sleep(random.uniform(0.3, 1.5))
                await asyncio.to_thread(axis.stopScan)
                epos = await asyncio.to_thread(axis.getEPOS)
                with position_lock:
                    current_position = epos
            await asyncio.sleep(random.uniform(0.2, 0.8))

        logger.info("Demo completed")
    except Exception as e:
        logger.error(f"Demo error: {e}")
    finally:
        demo_running = False
        if axis:
            await asyncio.to_thread(axis.stopScan)
            await asyncio.to_thread(axis.setDPOS, 0)
            with position_lock:
                current_position = 0


# ===== BACKGROUND TASKS =====
async def send_camera_frames(websocket):
    global picam2, last_successful_frame_time, last_movement_time, current_fps
    frame_count = 0
    last_frame_time = time.time()
    frame_backlog = 0

    logger.info("Starting frame sender")
    while not shutdown_requested:
        try:
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / current_fps)
                frame_count += 1
                continue

            if not picam2 or not hasattr(picam2,
                                         'started') or not picam2.started:
                logger.warning("Camera unavailable - reinitializing")
                initialize_camera()
                await asyncio.sleep(1)
                continue

            # Adjust FPS based on last movement time
            current_time = time.time()
            time_since_movement = current_time - last_movement_time
            previous_fps = current_fps
            if time_since_movement > MOVEMENT_TIMEOUT:
                current_fps = LOW_FPS
            else:
                current_fps = TARGET_FPS

            if current_fps != previous_fps:
                logger.info(
                    f"Adjusted FPS to {current_fps} (time since last movement: {time_since_movement:.1f}s)"
                )

            capture_time = time.time()
            frame_interval = 1.0 / current_fps
            elapsed = capture_time - last_frame_time

            if elapsed > frame_interval * 2:
                frame_backlog += 1
                if frame_backlog % 10 == 0:
                    logger.debug(f"Backlog: {frame_backlog}")
            else:
                frame_backlog = max(0, frame_backlog - 1)

            last_frame_time = capture_time
            try:
                frame = picam2.capture_array("main")
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Capture error: {e}")
                continue

            encode_time = time.time()
            jpeg_quality = max(30, JPEG_QUALITY - (frame_backlog // 5) * 10)
            try:
                buffer = await encode_jpeg_async(frame, jpeg_quality)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encode error: {e}")
                continue

            send_time = time.time()
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            frame_data = {
                "type":
                "camera_frame",
                "rpiId":
                STATION_ID,
                "frame":
                jpg_as_text,
                "timestamp":
                frame_time,
                "frameNumber":
                frame_count,
                "idString":
                f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
            }
            try:
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_successful_frame_time = time.time()

                if frame_count % 30 == 0:
                    latency = {
                        "capture_ms": (encode_time - capture_time) * 1000,
                        "encode_ms": (send_time - encode_time) * 1000,
                        "send_ms": (time.time() - send_time) * 1000
                    }
                    latency_log.append(latency)
                    logger.debug(f"Frame {frame_count}: {latency}")
            except Exception as e:
                logger.error(f"Send error: {e}")
                continue

        except Exception as e:
            logger.error(f"Frame sender error: {e}")
            await asyncio.sleep(0.1)


async def send_position_updates(websocket):
    global axis, last_successful_command_time, current_position
    last_epos = None
    last_update_time = time.time()

    logger.info("Starting position updates")
    while not shutdown_requested:
        try:
            if not RUNNING_ON_RPI or not axis:
                await asyncio.sleep(1)
                continue

            current_time = time.time()
            elapsed = current_time - last_update_time
            if elapsed < EPOS_UPDATE_INTERVAL:
                await asyncio.sleep(EPOS_UPDATE_INTERVAL - elapsed)
                continue

            last_update_time = current_time
            try:
                epos = await asyncio.to_thread(axis.getEPOS)
                with position_lock:
                    current_position = epos
                if last_epos != epos or elapsed > 1.0:
                    position_data = {
                        "type": "position_update",
                        "rpiId": STATION_ID,
                        "epos": epos,
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(position_data))
                    last_epos = epos
                    last_successful_command_time = time.time()
                    logger.debug(f"Position: {epos:.6f} mm")
            except Exception as e:
                logger.error(f"Position error: {e}")
        except Exception as e:
            logger.error(f"Position update error: {e}")
            await asyncio.sleep(0.5)


async def health_checker(websocket):
    global startup_time, thermal_error_count, amplifier_error_count, serial_error_count
    logger.info("Starting health monitor")
    while not shutdown_requested:
        try:
            current_time = time.time()
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            ping_silence = current_time - last_ping_response_time
            uptime = current_time - startup_time

            if int(uptime) % 60 == 0:
                logger.info(
                    f"Uptime: {uptime:.1f}s, Errors: {thermal_error_count}/{amplifier_error_count}/{serial_error_count}"
                )

            health_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID,
                "uptime": uptime,
                "errors": {
                    "thermal": thermal_error_count,
                    "amplifier": amplifier_error_count,
                    "serial": serial_error_count
                }
            }
            try:
                await asyncio.wait_for(websocket.send(json.dumps(health_data)),
                                       timeout=2.0)
            except asyncio.TimeoutError:
                logger.error("Health send timeout")
                break

            ping_data = {
                "type": "ping",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID
            }
            try:
                await asyncio.wait_for(websocket.send(json.dumps(ping_data)),
                                       timeout=1.0)
            except asyncio.TimeoutError:
                logger.error("Ping timeout")
                break

            await asyncio.sleep(CONNECTION_HEARTBEAT_INTERVAL)
        except Exception as e:
            logger.error(f"Health error: {e}")
            break


async def flush_buffers():
    global picam2
    logger.info("Starting buffer flush")
    while not shutdown_requested:
        try:
            if RUNNING_ON_RPI and picam2 and hasattr(
                    picam2,
                    'started') and picam2.started and frame_backlog > 2:
                for _ in range(2):
                    _ = picam2.capture_array("main")
                logger.debug("Camera buffers flushed")
            if RUNNING_ON_RPI and os.path.exists(COM_PORT):
                flush_serial_port()  # Flush serial port every 3 seconds
            gc.collect()
            await asyncio.sleep(BUFFER_FLUSH_INTERVAL)
        except Exception as e:
            logger.error(f"Buffer flush error: {e}")
            await asyncio.sleep(1)


async def command_processor():
    logger.info("Starting command processor")
    while not shutdown_requested:
        try:
            try:
                command = await asyncio.wait_for(command_queue.get(),
                                                 timeout=0.5)
            except asyncio.TimeoutError:
                continue

            websocket = getattr(command_processor, 'websocket', None)
            if websocket:
                await websocket.send(json.dumps(command))
                logger.debug(f"Sent command: {command.get('type')}")
        except Exception as e:
            logger.error(f"Command processor error: {e}")
            await asyncio.sleep(0.5)


# ===== MAIN CLIENT FUNCTION =====
async def rpi_client():
    global shutdown_requested, reconnect_delay, total_connection_failures, startup_time, demo_running
    startup_time = time.time()
    logger.info(f"Starting client for {STATION_ID}")

    if RUNNING_ON_RPI:
        os.system("sudo chrt -r -p 20 $$")

    if RUNNING_ON_RPI:
        initialize_camera()
        initialize_xeryon_controller()

    connection_id = f"bp_{int(time.time())}"
    buffer_task = asyncio.create_task(flush_buffers())
    cmd_processor_task = asyncio.create_task(command_processor())

    while not shutdown_requested:
        try:
            logger.info(
                f"Connecting to {SERVER_URL} (attempt {total_connection_failures + 1})"
            )
            websocket = await asyncio.wait_for(websockets.connect(
                SERVER_URL,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=MAX_CLOSE_TIMEOUT,
                max_size=10_000_000,
                compression=None),
                                               timeout=MAX_CONNECTION_TIMEOUT)
            logger.info("WebSocket connected")

            registration_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined",
                "status": "ready",
                "message": f"RPi {STATION_ID} initialized (Bulletproof v2.1)",
                "connectionId": connection_id,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(registration_message))
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
                        ping_data = {
                            "type": "ping",
                            "timestamp": datetime.now().isoformat(),
                            "rpiId": STATION_ID
                        }
                        await websocket.send(json.dumps(ping_data))
                        continue

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
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}")
                    except Exception as e:
                        logger.error(f"Message error: {e}")

            except websockets.exceptions.ConnectionClosed:
                logger.error("WebSocket closed")
            finally:
                for task in [frame_task, position_task, health_task]:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(frame_task,
                                     position_task,
                                     health_task,
                                     return_exceptions=True)

            logger.info("Tasks stopped, reconnecting")
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Connection error: {e}")
            total_connection_failures += 1
            if "device not connected" in str(
                    e).lower() or "cannot connect" in str(e).lower():
                actual_delay = 0.1
            else:
                reconnect_delay = min(
                    MAX_RECONNECT_DELAY,
                    RECONNECT_BASE_DELAY *
                    (1.2**min(total_connection_failures % 5, 4)))
                actual_delay = reconnect_delay + random.uniform(
                    0, 0.1 * reconnect_delay)

            if total_connection_failures < 3:
                actual_delay = min(0.1, actual_delay)
            logger.info(f"Retrying in {actual_delay:.2f}s")
            await asyncio.sleep(actual_delay)

            if total_connection_failures % 3 == 0:
                logger.warning("Multiple failures, resetting hardware")
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
    global shutdown_requested
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        await rpi_client()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await shutdown()


async def shutdown():
    global shutdown_requested
    if shutdown_requested:
        return

    shutdown_requested = True
    logger.info("Shutting down")
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
        logger.error(f"Critical error: {e}")
        if RUNNING_ON_RPI:
            try:
                stop_camera()
                stop_controller()
            except:
                pass
