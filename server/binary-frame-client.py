#!/usr/bin/env python3
"""
Optimized Raspberry Pi Client with Binary WebSocket Frame Transmission
- Sends raw JPEG frames directly via binary WebSocket messages
- Eliminates base64 encoding/decoding overhead
- Reduces bandwidth usage and improves performance
- Maintains all other functionality of the bulletproof client
"""

import asyncio
import json
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
import struct
from concurrent.futures import ThreadPoolExecutor

# Will be imported on the actual RPi
try:
    from picamera2 import Picamera2
    import websockets
    from websockets.exceptions import ConnectionClosed
    import cv2
    import serial
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
except ImportError:
    RUNNING_ON_RPI = False

    # Create mock classes for development
    class ConnectionClosed(Exception):
        pass
    
    # Mock cv2 for simulation
    class MockCV2:
        IMWRITE_JPEG_QUALITY = 1
        IMWRITE_JPEG_OPTIMIZE = 2
        IMWRITE_JPEG_PROGRESSIVE = 3
        FONT_HERSHEY_SIMPLEX = 0
        
        @staticmethod
        def imencode(ext, frame, params):
            return True, b'mock_jpeg_data'
        
        @staticmethod
        def putText(frame, text, pos, font, size, color, thickness):
            pass
        
        @staticmethod
        def cvtColor(img, code):
            return img

    cv2 = MockCV2()
    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 50
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.2  # 50ms position update interval
COMMAND_TIMEOUT = 60

# Protocol configuration for binary frames
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

# ===== HELPER FUNCTIONS FOR HARDWARE =====

def flush_serial_port():
    """Aggressively flush serial port to avoid buffer issues."""
    if not RUNNING_ON_RPI or not controller:
        return
    
    try:
        logger.debug("Aggressively flushing serial port")
        
        # Try standard flush first
        controller.port.reset_input_buffer()
        controller.port.reset_output_buffer()
        
        # Force a complete reset if serial port exists
        if hasattr(controller, 'port') and controller.port:
            try:
                # Get the current port settings
                port_name = controller.port.name
                port_baudrate = controller.port.baudrate
                port_timeout = controller.port.timeout
                
                # Close it
                controller.port.close()
                
                # Wait a moment for OS to clear resources
                time.sleep(0.1)
                
                # Reopen it
                controller.port = serial.Serial(
                    port=port_name,
                    baudrate=port_baudrate,
                    timeout=port_timeout
                )
                
                logger.debug(f"Successfully reopened serial port {port_name}")
            except Exception as e:
                logger.error(f"Error during aggressive serial port flush: {e}")
    except Exception as e:
        logger.error(f"Failed to flush serial port: {e}")

def initialize_camera():
    """Initialize camera with robust error handling."""
    global picam2
    
    if not RUNNING_ON_RPI:
        logger.info("Camera initialization skipped (not on RPi)")
        return True
    
    try:
        logger.info("Initializing camera with robust error handling")
        
        # Kill any lingering camera processes that might be blocking access
        try:
            subprocess.run("pkill -f picamera2", shell=True)
            time.sleep(1)  # Give time for processes to terminate
        except Exception as e:
            logger.warning(f"Error killing existing picamera2 processes: {e}")
        
        if picam2 is not None:
            try:
                picam2.close()
            except:
                pass
            picam2 = None
            
        # Force garbage collection to release any dangling camera references
        gc.collect()
        
        # Initialize with retries
        max_tries = 5
        for attempt in range(max_tries):
            try:
                logger.debug(f"Camera initialization attempt {attempt+1}/{max_tries}")
                
                picam2 = Picamera2()
                
                # Configure camera for optimal responsiveness with higher framerate
                config = picam2.create_video_configuration(
                    main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"},
                    controls={"FrameDurationLimits": (16666, 33333)}  # 30-60 fps range
                )
                
                picam2.configure(config)
                picam2.start()
                
                logger.info("Camera initialized successfully")
                return True
            except Exception as e:
                logger.error(f"Camera initialization attempt {attempt+1} failed: {e}")
                if "Pipeline handler in use by another process" in str(e):
                    # Another process is using the camera, try more aggressively to kill it
                    try:
                        subprocess.run("sudo pkill -9 -f picamera2", shell=True)
                        time.sleep(2)  # Give more time for forceful termination
                    except Exception as e2:
                        logger.warning(f"Error forcefully killing picamera2 processes: {e2}")
                
                # Sleep between attempts with increasing delays
                time.sleep(1 * (attempt + 1))
                
                # Force garbage collection again
                gc.collect()
        
        logger.error(f"Camera initialization failed after {max_tries} attempts")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in camera initialization: {e}")
        return False

def stop_camera():
    """Safely stop and release camera resources."""
    global picam2
    
    if not RUNNING_ON_RPI or picam2 is None:
        return
    
    try:
        logger.info("Stopping camera")
        picam2.close()
        picam2 = None
        logger.info("Camera stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping camera: {e}")

def initialize_xeryon_controller():
    """Initialize Xeryon controller with comprehensive error handling."""
    global controller, axis
    
    if not RUNNING_ON_RPI:
        logger.info("Xeryon controller initialization skipped (not on RPi)")
        return True
    
    try:
        logger.info("Initializing Xeryon controller")
        
        # Set up the controller with retries
        max_tries = 5
        for attempt in range(max_tries):
            try:
                logger.debug(f"Xeryon controller initialization attempt {attempt+1}/{max_tries}")
                
                # Close any existing controller
                if controller is not None:
                    try:
                        controller.close()
                    except:
                        pass
                    controller = None
                
                # Open a new one
                controller = Xeryon(COM_PORT, 115200)
                axis = controller.stages[0]
                
                # Configure safe initial parameters
                axis.set_speed(DEFAULT_SPEED)
                axis.set_acce(DEFAULT_ACCELERATION)
                axis.set_dece(DEFAULT_DECELERATION)
                
                # Verify controller is responding
                current_pos = axis.get_pos(Units.MM)
                logger.info(f"Controller initialized successfully. Current position: {current_pos}mm")
                
                # Set global position
                with position_lock:
                    global current_position
                    current_position = current_pos
                
                return True
            except Exception as e:
                logger.error(f"Controller initialization attempt {attempt+1} failed: {e}")
                
                # Check for specific errors
                error_str = str(e).lower()
                if "permission denied" in error_str:
                    logger.warning("Permission denied on serial port. Check permissions.")
                elif "device busy" in error_str:
                    logger.warning("Device busy. Attempting to free serial port.")
                    try:
                        subprocess.run(f"fuser -k {COM_PORT}", shell=True)
                        time.sleep(2)
                    except:
                        pass
                
                # Sleep between attempts with increasing delays
                time.sleep(1 * (attempt + 1))
        
        logger.error(f"Controller initialization failed after {max_tries} attempts")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in controller initialization: {e}")
        return False

def stop_controller():
    """Safely stop and release Xeryon controller."""
    global controller, axis
    
    if not RUNNING_ON_RPI or controller is None:
        return
    
    try:
        logger.info("Stopping Xeryon controller")
        
        # Set to safe acceleration/deceleration values before stopping
        try:
            axis.set_acce(DEFAULT_ACCELERATION)
            axis.set_dece(DEFAULT_DECELERATION)
            axis.stop()
        except Exception as e:
            logger.error(f"Error stopping motion: {e}")
        
        # Close controller
        controller.close()
        controller = None
        axis = None
        logger.info("Xeryon controller stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping controller: {e}")

def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration parameters with error handling."""
    if not RUNNING_ON_RPI or controller is None or axis is None:
        return True
    
    try:
        if acce_value is not None:
            logger.debug(f"Setting acceleration to {acce_value}")
            axis.set_acce(int(acce_value))
        
        if dece_value is not None:
            logger.debug(f"Setting deceleration to {dece_value}")
            axis.set_dece(int(dece_value))
        
        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece parameters: {e}")
        return False

# ===== CAMERA FRAME HANDLING WITH BINARY WEBSOCKET =====

async def encode_jpeg_async(frame, quality):
    """Encode frame to JPEG asynchronously using a thread pool."""
    return await asyncio.to_thread(encode_jpeg, frame, quality)

def encode_jpeg(frame, quality):
    """Encode frame to JPEG with specified quality."""
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
    """Send camera frames as binary WebSocket messages for maximum efficiency."""
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
                    # Explicitly capture and discard a frame to flush any pending frames
                    try:
                        _ = picam2.capture_array("main")  # Capture and discard
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
                last_flush_time = current_time

            # Check if camera is available
            if not RUNNING_ON_RPI:
                # Simulation mode - create a test frame
                if frame_count % 100 == 0:
                    logger.info(f"Simulation mode - sending test frame #{frame_count}")
                
                # Create mock binary data for testing
                timestamp = int(time.time() * 1000)
                header = struct.pack(FRAME_HEADER_FORMAT,
                                    STATION_ID.encode()[:4].ljust(4),
                                    frame_count,
                                    timestamp)
                
                # Mock JPEG data with frame number embedded
                mock_jpeg = f"TESTFRAME{frame_count}".encode() * 1000
                
                # Send binary test data
                binary_data = header + mock_jpeg
                try:
                    await websocket.send(binary_data)
                    frame_count += 1
                    last_successful_frame_time = time.time()
                except Exception as e:
                    logger.error(f"Error sending test frame: {e}")
                
                await asyncio.sleep(1.0 / TARGET_FPS)
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

            # Skip frames if we're falling behind to prioritize showing the most current image
            if elapsed > frame_interval * 2:
                frame_backlog += 1
                if frame_backlog % 10 == 0:
                    logger.debug(f"Frame sender falling behind (backlog: {frame_backlog}) - prioritizing freshness")
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

            # Add frame info overlay
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
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
                jpeg_quality = max(30, JPEG_QUALITY - (frame_backlog // 5) * 10)

            # Encode with threaded JPEG encoder - returns directly as bytes, no base64
            try:
                buffer = await encode_jpeg_async(frame, jpeg_quality)
                
                # Create binary frame header
                # Encode station ID and frame info in a fixed binary header 
                # This allows the server to identify the source without parsing JSON
                timestamp = int(time.time() * 1000)  # milliseconds since epoch
                header = struct.pack(FRAME_HEADER_FORMAT,
                                    STATION_ID.encode()[:4].ljust(4),  # Force 4 chars
                                    frame_count,
                                    timestamp)
                
                # Combine header and JPEG data
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

            # Minimal recovery sleep at end of frame transmission
            await asyncio.sleep(MIN_SLEEP_DELAY)

        except Exception as e:
            logger.error(f"Camera frame task error: {str(e)}")
            await asyncio.sleep(0.5)  # Slightly longer sleep on error

# ===== COMMAND PROCESSING =====

async def process_command(data):
    """Process incoming commands with comprehensive error handling and safety checks."""
    global current_position, controller, axis
    
    try:
        command = data.get('command', '').lower()
        direction = data.get('direction', '').lower()
        step_size = float(data.get('stepSize', 1.0))
        step_unit = data.get('stepUnit', 'mm').lower()
        
        # Convert from other units to mm if needed
        if step_unit == 'μm' or step_unit == 'um':
            step_size = step_size / 1000.0
        elif step_unit == 'nm':
            step_size = step_size / 1000000.0
        
        logger.info(f"Processing command: {command}, direction: {direction}, step size: {step_size} mm")
        
        # Safety check - verify controller is available
        if not RUNNING_ON_RPI or controller is None or axis is None:
            if not RUNNING_ON_RPI:
                logger.info(f"Simulation mode - mock command: {command}, direction: {direction}, step: {step_size}")
                
                # Update simulated position
                with position_lock:
                    if command == "step":
                        if direction == "left":
                            current_position -= step_size
                        elif direction == "right":
                            current_position += step_size
                    elif command == "home":
                        current_position = 0.0
                    
                    # Simulation safety bounds
                    current_position = max(-30.0, min(30.0, current_position))
                    logger.info(f"Simulated position updated to {current_position} mm")
                
                return {"status": "success", "message": f"Command {command} simulated"}
            else:
                logger.error("Controller not available")
                return {"status": "error", "message": "Controller not available"}
        
        # Handle different command types
        if command == "step":
            # Calculate the target position
            with position_lock:
                current_pos = current_position
                
            if direction == "left":
                target_pos = current_pos - step_size
            elif direction == "right":
                target_pos = current_pos + step_size
            else:
                return {"status": "error", "message": "Invalid direction"}
            
            # Safety check - ensure position is within bounds (-30mm to +30mm)
            if target_pos < -30.0 or target_pos > 30.0:
                logger.warning(f"Position {target_pos} is out of bounds (-30mm to +30mm)")
                return {"status": "error", "message": "Position out of bounds"}
            
            # Execute the move
            try:
                axis.move_to(target_pos, Units.MM)
                
                # Update the current position
                with position_lock:
                    current_position = axis.get_pos(Units.MM)
                
                logger.info(f"Step executed. New position: {current_position}")
                return {"status": "success", "message": f"Step to {current_position:.3f} mm"}
            except Exception as e:
                logger.error(f"Error executing step: {e}")
                
                # Check for thermal protection error
                error_str = str(e).lower()
                if "thermal protection" in error_str or "protection thermique" in error_str:
                    logger.critical("THERMAL PROTECTION ERROR DETECTED!")
                    return {"status": "error", "message": "Thermal protection activated. Please wait for cooling."}
                elif "amplifier" in error_str:
                    logger.critical("AMPLIFIER ERROR DETECTED!")
                    return {"status": "error", "message": "Amplifier error. Controller needs reset."}
                else:
                    return {"status": "error", "message": f"Step error: {e}"}
        
        elif command == "home":
            # Move to home position (0.0 mm)
            try:
                axis.move_to(0.0, Units.MM)
                
                # Update the current position
                with position_lock:
                    current_position = axis.get_pos(Units.MM)
                
                logger.info(f"Homed to position: {current_position}")
                return {"status": "success", "message": f"Homed to {current_position:.3f} mm"}
            except Exception as e:
                logger.error(f"Error homing: {e}")
                return {"status": "error", "message": f"Home error: {e}"}
        
        elif command == "stop":
            # Immediately stop motion
            try:
                axis.stop()
                
                # Update the current position
                with position_lock:
                    current_position = axis.get_pos(Units.MM)
                
                logger.info(f"Motion stopped. Position: {current_position}")
                return {"status": "success", "message": f"Stopped at {current_position:.3f} mm"}
            except Exception as e:
                logger.error(f"Error stopping: {e}")
                return {"status": "error", "message": f"Stop error: {e}"}
        
        elif command == "set_acce":
            # Set acceleration parameter
            try:
                acce_value = int(data.get('value', DEFAULT_ACCELERATION))
                success = set_acce_dece_params(acce_value=acce_value)
                
                if success:
                    logger.info(f"Acceleration set to {acce_value}")
                    return {"status": "success", "message": f"Acceleration set to {acce_value}"}
                else:
                    return {"status": "error", "message": "Failed to set acceleration"}
            except Exception as e:
                logger.error(f"Error setting acceleration: {e}")
                return {"status": "error", "message": f"Acceleration error: {e}"}
        
        elif command == "set_dece":
            # Set deceleration parameter
            try:
                dece_value = int(data.get('value', DEFAULT_DECELERATION))
                success = set_acce_dece_params(dece_value=dece_value)
                
                if success:
                    logger.info(f"Deceleration set to {dece_value}")
                    return {"status": "success", "message": f"Deceleration set to {dece_value}"}
                else:
                    return {"status": "error", "message": "Failed to set deceleration"}
            except Exception as e:
                logger.error(f"Error setting deceleration: {e}")
                return {"status": "error", "message": f"Deceleration error: {e}"}
        
        elif command == "set_speed":
            # Set speed parameter
            try:
                speed_value = int(data.get('value', DEFAULT_SPEED))
                
                if controller and axis:
                    axis.set_speed(speed_value)
                    logger.info(f"Speed set to {speed_value}")
                    return {"status": "success", "message": f"Speed set to {speed_value}"}
                else:
                    return {"status": "error", "message": "Controller not available"}
            except Exception as e:
                logger.error(f"Error setting speed: {e}")
                return {"status": "error", "message": f"Speed error: {e}"}
        
        elif command == "run_demo":
            # Start the demo sequence
            asyncio.create_task(run_demo())
            return {"status": "success", "message": "Demo started"}
        
        else:
            logger.warning(f"Unknown command: {command}")
            return {"status": "error", "message": "Unknown command"}
    
    except Exception as e:
        logger.error(f"Error processing command: {e}")
        return {"status": "error", "message": f"Command processing error: {e}"}

async def run_demo():
    """Run a safe demo sequence that showcases the capabilities of the actuator."""
    global demo_running, current_position
    
    if demo_running:
        logger.info("Demo already running")
        return
    
    try:
        demo_running = True
        logger.info("Starting demo sequence")
        
        if not RUNNING_ON_RPI or controller is None or axis is None:
            # Simulation mode demo
            logger.info("Running simulated demo")
            
            # Simulate movement 
            positions = []
            current_pos = 0
            
            # Generate a random sequence of positions
            num_positions = random.randint(10, 20)
            for i in range(num_positions):
                # Random position between -30 and +30
                pos = random.uniform(-28, 28)
                positions.append(pos)
            
            # Add home position at the end
            positions.append(0)
            
            # Move through the positions
            for pos in positions:
                if shutdown_requested:
                    break
                
                # Update simulated position
                with position_lock:
                    # Gradually move towards target
                    steps = 10
                    start_pos = current_position
                    for step in range(steps):
                        if shutdown_requested:
                            break
                        
                        # Linear interpolation
                        current_position = start_pos + (pos - start_pos) * (step + 1) / steps
                        logger.info(f"Demo simulated position: {current_position:.3f} mm")
                        await asyncio.sleep(0.5)  # Simulate movement time
            
            logger.info("Simulated demo completed")
        
        else:
            # Real hardware demo
            logger.info("Running hardware demo")
            
            # Set default parameters
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            axis.set_speed(DEFAULT_SPEED)
            
            # Move to starting position
            logger.info("Moving to starting position (0.0 mm)")
            axis.move_to(0.0, Units.MM)
            await asyncio.sleep(2)
            
            # Get current position
            with position_lock:
                current_position = axis.get_pos(Units.MM)
            
            # Generate a safe yet varied demo sequence
            positions = []
            
            # Add random positions between -25mm and +25mm
            num_positions = random.randint(8, 15)
            for i in range(num_positions):
                speed = random.randint(100, 1000)  # Varied speeds
                acce = random.randint(1000, 65000)  # Varied accelerations
                dece = random.randint(1000, 65000)  # Varied decelerations
                pos = random.uniform(-25, 25)  # Safe range
                
                positions.append({
                    "position": pos,
                    "speed": speed,
                    "acce": acce,
                    "dece": dece
                })
            
            # Add home position at the end
            positions.append({
                "position": 0.0,
                "speed": DEFAULT_SPEED,
                "acce": DEFAULT_ACCELERATION,
                "dece": DEFAULT_DECELERATION
            })
            
            # Execute the sequence
            for idx, params in enumerate(positions):
                if shutdown_requested:
                    break
                
                # Set motion parameters
                set_acce_dece_params(params["acce"], params["dece"])
                axis.set_speed(params["speed"])
                
                # Log the planned move
                logger.info(f"Demo step {idx+1}/{len(positions)}: "
                          f"Moving to {params['position']:.3f} mm "
                          f"(Speed: {params['speed']}, Acce: {params['acce']}, Dece: {params['dece']})")
                
                # Execute the move
                axis.move_to(params["position"], Units.MM)
                
                # Wait for move to complete or timeout
                start_time = time.time()
                while time.time() - start_time < 10:  # 10 second timeout
                    if shutdown_requested:
                        break
                    
                    # Update position
                    with position_lock:
                        current_position = axis.get_pos(Units.MM)
                    
                    # Check if we've reached the target
                    if abs(current_position - params["position"]) < 0.1:
                        break
                    
                    await asyncio.sleep(0.1)
            
            # Reset to default parameters
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            axis.set_speed(DEFAULT_SPEED)
            
            logger.info("Demo sequence completed")
    
    except Exception as e:
        logger.error(f"Error in demo sequence: {e}")
    
    finally:
        demo_running = False

async def send_position_updates(websocket):
    """Send position updates at regular intervals."""
    global current_position
    
    logger.info("Starting position update sender task")
    
    while not shutdown_requested:
        try:
            # Prepare position update message
            with position_lock:
                pos = current_position
            
            message = {
                "type": "position_update",
                "rpiId": STATION_ID,
                "epos": pos
            }
            
            # Send position update
            await websocket.send(json.dumps(message))
            
            # Wait for next update interval
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
        
        except Exception as e:
            logger.error(f"Error sending position update: {e}")
            await asyncio.sleep(1)  # Longer delay on error

async def health_checker(websocket):
    """Monitor and report on system health."""
    global last_successful_command_time, last_successful_frame_time, last_ping_response_time
    
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
                    "timestamp": datetime.now().isoformat(),
                    "uptime": int(current_time - startup_time) if startup_time else 0
                }
                
                try:
                    await websocket.send(json.dumps(ping_message))
                    logger.debug("Sent ping message for latency measurement")
                    last_ping_time = current_time
                except Exception as e:
                    logger.error(f"Error sending ping: {e}")
            
            # Check for camera and controller health
            if RUNNING_ON_RPI:
                # Check camera health
                if picam2 is None or not hasattr(picam2, 'started') or not picam2.started:
                    logger.warning("Health check: Camera not initialized or not running")
                    initialize_camera()
                
                # Check controller health
                if controller is None or axis is None:
                    logger.warning("Health check: Controller not initialized")
                    initialize_xeryon_controller()
                
                # Check for long-running frame transmission issues
                if current_time - last_successful_frame_time > 10:
                    logger.warning(f"Health check: No frames sent for {current_time - last_successful_frame_time:.1f} seconds")
                
                # Check for ping response timeouts
                if current_time - last_ping_response_time > 15:
                    logger.warning(f"Health check: No ping responses for {current_time - last_ping_response_time:.1f} seconds")
            
            # Aggressive buffer flushing every 15 seconds
            if RUNNING_ON_RPI and current_time % 15 < 1 and controller is not None:
                flush_serial_port()
            
            # Brief sleep to prevent excessive CPU usage
            await asyncio.sleep(1.0)
        
        except Exception as e:
            logger.error(f"Error in health checker: {e}")
            await asyncio.sleep(2.0)

async def flush_buffers():
    """Aggressively flush all buffers to prevent data buildup."""
    logger.info("Starting buffer flush task")
    
    while not shutdown_requested:
        try:
            if RUNNING_ON_RPI:
                # Flush serial port
                if controller is not None:
                    flush_serial_port()
                
                # Flush camera frames if needed
                if picam2 is not None and hasattr(picam2, 'started') and picam2.started:
                    try:
                        # Capture and discard a frame to clear buffer
                        _ = picam2.capture_array("main")
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
            
            # Wait before next flush
            await asyncio.sleep(15.0)  # Flush every 15 seconds
        
        except Exception as e:
            logger.error(f"Error in buffer flush task: {e}")
            await asyncio.sleep(5.0)

async def command_processor():
    """Process queued commands in the background."""
    logger.info("Starting command processor task")
    
    while not shutdown_requested:
        try:
            # Get a command from the queue with timeout
            try:
                command_data = await asyncio.wait_for(command_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No commands in queue, continue to next iteration
                continue
            
            # Process the command
            response = await process_command(command_data)
            
            # Send the response if needed
            if command_data.get('_websocket') and command_data.get('_respond', True):
                # Add response metadata
                response['type'] = 'command_response'
                response['command'] = command_data.get('command')
                response['timestamp'] = datetime.now().isoformat()
                
                try:
                    await command_data['_websocket'].send(json.dumps(response))
                except Exception as e:
                    logger.error(f"Error sending command response: {e}")
            
            # Mark command as complete
            command_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in command processor: {e}")
            await asyncio.sleep(1.0)

async def rpi_client():
    """Main client function with robust connection and error handling."""
    global startup_time, last_ping_response_time, total_connection_failures, reconnect_delay
    
    startup_time = time.time()
    logger.info(f"Starting Raspberry Pi client for {STATION_ID}")
    logger.info(f"Connecting to {SERVER_URL}")
    
    # Start with the base reconnect delay
    reconnect_delay = RECONNECT_BASE_DELAY
    connection_attempt = 0
    
    while not shutdown_requested:
        try:
            connection_attempt += 1
            logger.info(f"Connection attempt {connection_attempt} (reconnect delay: {reconnect_delay:.1f}s)")
            
            # Connect with timeout
            try:
                websocket = await asyncio.wait_for(
                    websockets.connect(SERVER_URL, ping_interval=None),  # Disable ping/pong mechanism
                    timeout=MAX_CONNECTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(f"Connection attempt timed out after {MAX_CONNECTION_TIMEOUT}s")
                total_connection_failures += 1
                
                # Implement exponential backoff with jitter for reconnection
                reconnect_delay = min(reconnect_delay * 1.5, MAX_RECONNECT_DELAY)
                reconnect_delay *= (0.9 + 0.2 * random.random())  # Add jitter
                
                await asyncio.sleep(reconnect_delay)
                continue
            
            # Connection successful, reset failure counts
            total_connection_failures = 0
            reconnect_delay = RECONNECT_BASE_DELAY
            logger.info("Connected to server")
            
            # Register with server
            await websocket.send(json.dumps({
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }))
            logger.info("Sent registration message")
            
            # Initialize resources
            if RUNNING_ON_RPI:
                # Initialize hardware
                initialize_camera()
                initialize_xeryon_controller()
                
                # Set default parameters
                if controller and axis:
                    set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
                    axis.set_speed(DEFAULT_SPEED)
            
            # Start background tasks
            tasks = []
            tasks.append(asyncio.create_task(send_camera_frames(websocket)))
            tasks.append(asyncio.create_task(send_position_updates(websocket)))
            tasks.append(asyncio.create_task(health_checker(websocket)))
            tasks.append(asyncio.create_task(flush_buffers()))
            tasks.append(asyncio.create_task(command_processor()))
            
            # Main message processing loop
            while not shutdown_requested:
                try:
                    # Receive message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    
                    # Process message
                    try:
                        data = json.loads(message)
                        message_type = data.get('type', '')
                        
                        if message_type == 'pong':
                            # Update the last ping response time
                            last_ping_response_time = time.time()
                            logger.debug("Received pong response")
                        
                        elif message_type == 'command':
                            # Add the websocket to the command data for response
                            data['_websocket'] = websocket
                            
                            # Log command receipt
                            command = data.get('command', 'unknown')
                            direction = data.get('direction', 'none')
                            step_size = data.get('stepSize', 0)
                            logger.info(f"Received command: {command}, dir: {direction}, size: {step_size}")
                            
                            # Enqueue the command for processing
                            await command_queue.put(data)
                    
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON received: {message[:100]}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                
                except asyncio.TimeoutError:
                    # This is normal - no messages received within timeout
                    pass
                except ConnectionClosed:
                    logger.warning("Connection closed by server")
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    break
            
            # Clean up tasks when the main loop exits
            for task in tasks:
                task.cancel()
            
            # Clean up websocket
            try:
                await asyncio.wait_for(websocket.close(), timeout=MAX_CLOSE_TIMEOUT)
            except (asyncio.TimeoutError, Exception):
                pass
            
            logger.info("Connection closed, will reconnect")
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
        
        # Delay before reconnection attempt
        await asyncio.sleep(reconnect_delay)

async def main():
    """Entry point with proper signal handling and cleanup."""
    global shutdown_requested
    
    try:
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
        
        logger.info("Binary Frame Client (BFC) starting")
        
        # Run the client
        await rpi_client()
    
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    
    finally:
        # Ensure cleanup happens
        if not shutdown_requested:
            await shutdown()

async def shutdown():
    """Clean shutdown procedure."""
    global shutdown_requested
    
    if shutdown_requested:
        return
    
    shutdown_requested = True
    logger.info("Shutting down...")
    
    # Stop hardware resources
    if RUNNING_ON_RPI:
        stop_camera()
        stop_controller()
    
    logger.info("Shutdown complete")

# ===== MAIN ENTRY POINT =====
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        shutdown_requested = True