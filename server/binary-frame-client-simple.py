#!/usr/bin/env python3
"""
Binary WebSocket Frame Version of Bulletproof Client
- Optimized camera frame transmission with binary WebSocket
- ONLY modified WebSocket camera frame handling
- Left all controller code intact
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


# IMPORTANT: We're keeping all the original controller functions unchanged
# We're only modifying the camera frame transmission to use binary WebSocket

# ===== MODIFIED CAMERA FRAME HANDLING WITH BINARY WEBSOCKET =====
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

async def send_camera_frames(websocket):
    """Send camera frames with binary WebSocket messages for maximum efficiency."""
    global picam2, last_successful_frame_time

    frame_count = 0
    last_frame_time = time.time()
    frame_backlog = 0
    delay_factor = 1.0  # Dynamically adjusted based on performance
    last_flush_time = time.time()

    logger.info("Starting binary camera frame sender task")

    while not shutdown_requested:
        try:
            # Regular buffer flush to prevent buildup
            current_time = time.time()
            if current_time - last_flush_time > 1.0:  # Flush every second
                if RUNNING_ON_RPI and picam2:
                    try:
                        _ = picam2.capture_array("main")  # Capture and discard
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
                last_flush_time = current_time

            # Check if camera is available
            if not RUNNING_ON_RPI:
                # Simulation mode - create a test frame after a short delay
                await asyncio.sleep(1.0 / 10.0)  # Simulate 10 FPS in non-RPi mode
                frame_count += 1
                continue

            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.warning("Camera not available - attempting to initialize")
                initialize_camera()
                await asyncio.sleep(1)
                continue

            # Real-time optimization: Calculate timing
            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time

            # Skip frames if falling behind
            if elapsed > frame_interval * 2:
                frame_backlog += 1
                if frame_backlog % 10 == 0:
                    logger.debug(f"Frame sender falling behind (backlog: {frame_backlog}) - prioritizing freshness")
            else:
                frame_backlog = max(0, frame_backlog - 1)
                
                # Brief sleep if ahead of schedule
                if elapsed < frame_interval:
                    await asyncio.sleep(min(frame_interval - elapsed, 0.005) * delay_factor)

            # Minimal sleep to prevent CPU hogging
            await asyncio.sleep(MIN_SLEEP_DELAY)

            # Capture frame
            last_frame_time = time.time()
            try:
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue

            # Add frame info overlay
            if hasattr(cv2, 'putText'):
                frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
                cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)
                
                # Add position overlay
                with position_lock:
                    pos_str = f"Position: {current_position:.3f} mm"
                cv2.putText(frame, pos_str, (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)

            # Adjust JPEG quality based on backlog
            jpeg_quality = JPEG_QUALITY
            if frame_backlog > 5:
                jpeg_quality = max(30, JPEG_QUALITY - (frame_backlog // 5) * 10)

            # Encode frame to JPEG
            try:
                buffer = await encode_jpeg_async(frame, jpeg_quality)
                
                # Create binary frame header with unsigned 32-bit integers
                timestamp = int(time.time() * 1000) % 0xFFFFFFFF  # Ensure fits in 32-bit unsigned
                frame_num = frame_count % 0xFFFFFFFF              # Ensure fits in 32-bit unsigned
                
                # Pack the header
                header = struct.pack(FRAME_HEADER_FORMAT,
                                    STATION_ID.encode()[:4].ljust(4),  # Force exactly 4 chars
                                    frame_num,
                                    timestamp)
                
                # Combine header and JPEG data - NO base64 encoding needed for binary format
                binary_data = header + buffer.tobytes()
                
                # Send as binary WebSocket message
                await websocket.send(binary_data)
                
                frame_count += 1
                last_successful_frame_time = time.time()
                
                if frame_count % 100 == 0:
                    logger.info(f"Sent {frame_count} binary frames")
                
            except Exception as e:
                logger.error(f"Frame encoding or sending error: {e}")
                await asyncio.sleep(0.01)
                continue

            # Minimal sleep at end of transmission
            await asyncio.sleep(MIN_SLEEP_DELAY)

        except Exception as e:
            logger.error(f"Camera frame task error: {e}")
            await asyncio.sleep(0.5)

# Include the rest of the original code here...
# (flush_serial_port, initialize_xeryon_controller, stop_controller, set_acce_dece_params, 
#  initialize_camera, stop_camera, process_command, run_demo, send_position_updates, etc.)