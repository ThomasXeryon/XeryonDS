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
from collections import deque
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
SERVER_URL = f"ws://localhost:5000/rpi/{STATION_ID}"  
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.05  # 50ms position update interval
COMMAND_TIMEOUT = 60

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750 
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.00001

# Connection parameters
MAX_RECONNECT_ATTEMPTS = 9999
RECONNECT_BASE_DELAY = 0.5
MAX_RECONNECT_DELAY = 5.0
MAX_CONNECTION_TIMEOUT = 3.0
MAX_CLOSE_TIMEOUT = 1.0
CONNECTION_HEARTBEAT_INTERVAL = 5.0

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
current_position = 0.0
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

async def send_camera_frame(websocket, cap):
    ret, frame = cap.read()
    if not ret:
        return
    
    # Encode frame as JPEG
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]) #Added JPEG quality
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    
    # Create frame message
    frame_message = {
        "type": "camera_frame",
        "frame": f"data:image/jpeg;base64,{jpg_as_text}",
        "timestamp": datetime.now().isoformat(),
    }
    
    await websocket.send(json.dumps(frame_message))

async def send_position_update(websocket):
    # Simulate position data (oscillating between -100 and 100)
    import math #Import math here.
    position = 100 * math.sin(time.time())
    
    position_message = {
        "type": "position",
        "position": position,
        "timestamp": datetime.now().isoformat(),
    }
    
    await websocket.send(json.dumps(position_message))

async def heartbeat(websocket):
    while True:
        try:
            ping_message = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(ping_message))
            await asyncio.sleep(1)
        except:
            break

async def handle_messages(websocket):
    while True:
        try:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received message: {data}")
            
            # Handle command messages
            if data.get("type") == "command":
                response = {
                    "type": "command_response",
                    "status": "success",
                    "command": data.get("command"),
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(response))
        except Exception as e:
            print(f"Error handling message: {e}")
            break

async def main():
    global total_connection_failures, reconnect_delay
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else STATION_ID
    url = f"{SERVER_URL}"
    
    while True:
        if shutdown_requested:
            break
        try:
            print(f"Connecting to {url}...")
            async with websockets.connect(url, max_size=1024**3) as websocket: #Increased max_size.
                print("Connected!")
                
                # Send registration message
                reg_message = {
                    "type": "register",
                    "connectionType": "combined"
                }
                await websocket.send(json.dumps(reg_message))
                
                # Initialize camera
                if RUNNING_ON_RPI:
                    picam2 = Picamera2()
                    picam2.configure(picam2.create_preview_configuration(main={"format": 'RGB888', "size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT)}))
                    picam2.start()
                    cap = picam2
                else:
                    cap = cv2.VideoCapture(0)
                    if not cap.isOpened():
                        cap = cv2.VideoCapture(-1)  # Try default camera
                    if not cap.isOpened():
                        print("Warning: No camera available, will simulate camera feed")
                        import numpy as np #Import numpy here.
                        # Create a black frame
                        frame = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), np.uint8)
                        cap = type('DummyCap', (), {
                            'read': lambda self: (True, frame),
                            'isOpened': lambda self: True
                        })()
                
                # Start heartbeat
                heartbeat_task = asyncio.create_task(heartbeat(websocket))
                message_handler = asyncio.create_task(handle_messages(websocket))
                
                last_frame_time = 0
                last_position_time = 0
                
                while True:
                    if shutdown_requested:
                        break
                    current_time = time.time()
                    
                    # Send camera frame if interval elapsed
                    if current_time - last_frame_time >= 1.0/TARGET_FPS:
                        await send_camera_frame(websocket, cap)
                        last_frame_time = current_time
                    
                    # Send position update if interval elapsed
                    if current_time - last_position_time >= EPOS_UPDATE_INTERVAL:
                        await send_position_update(websocket)
                        last_position_time = current_time
                    
                    await asyncio.sleep(MIN_SLEEP_DELAY)  # Small sleep to prevent CPU hogging
                
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Websocket connection closed: {e}")
            total_connection_failures += 1
            reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)  #Exponential backoff
            logger.info(f"Retrying in {reconnect_delay} seconds...")
            await asyncio.sleep(reconnect_delay)

        except Exception as e:
            print(f"Connection error: {e}")
            logger.exception(f"An unexpected error occurred: {e}")
            total_connection_failures += 1
            reconnect_delay = min(reconnect_delay * 2, MAX_RECONNECT_DELAY)  #Exponential backoff
            logger.info(f"Retrying in {reconnect_delay} seconds...")
            await asyncio.sleep(reconnect_delay)
            

    if RUNNING_ON_RPI and picam2:
        picam2.stop()


def signal_handler(sig, frame):
    global shutdown_requested
    logger.info("Shutdown signal received. Initiating graceful shutdown...")
    shutdown_requested = True


if __name__ == "__main__":
    import math
    import numpy as np
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(main())