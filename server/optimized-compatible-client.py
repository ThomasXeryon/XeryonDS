#!/usr/bin/env python3
"""
Ultra-Optimized Raspberry Pi Client for Xeryon Demo Station
- Zero-delay between button press and actuator movement
- Zero-lag between movement and camera display
- Super-reliable connection that never drops
- Compatible with all WebSocket library versions
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
import gc
import subprocess
from datetime import datetime
import threading
import signal
from concurrent.futures import ThreadPoolExecutor

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
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70  # Higher quality for clear images
TARGET_FPS = 30    # Target higher FPS
COM_PORT = "/dev/ttyACM0"
POSITION_UPDATE_INTERVAL = 0.01  # 10ms for ultra-fast position updates

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500
MIN_SLEEP_DELAY = 0.000001  # 1µs minimum sleep for ultra-responsiveness

# Flush intervals for real-time performance
CAMERA_FLUSH_INTERVAL = 0.1  # 100ms - flush camera buffer more frequently
SERIAL_FLUSH_INTERVAL = 3.0  # 3s - flush serial port every 3 seconds

# Connection parameters - Ultra-fast reconnection
MAX_RECONNECT_ATTEMPTS = 9999  # Effectively infinite retries
RECONNECT_BASE_DELAY = 0.05  # Ultra-fast 50ms base delay
MAX_RECONNECT_DELAY = 0.5  # Cap at just 500ms maximum
HEARTBEAT_INTERVAL = 2.0  # Send heartbeats every 2 seconds for tight connection monitoring

# ===== GLOBAL STATE =====
shutdown_requested = False
controller = None
axis = None
picam2 = None
demo_running = False
last_successful_command_time = time.time()
last_successful_frame_time = time.time()
last_ping_response_time = time.time()
last_serial_flush_time = time.time()
last_camera_flush_time = time.time()
startup_time = time.time()

# Tracking variables
position_lock = threading.Lock()
current_position = 0.0  # Current position in mm
thermal_error_count = 0
amplifier_error_count = 0
serial_error_count = 0
last_error_time = 0
last_frame_count = 0

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
jpeg_executor = ThreadPoolExecutor(max_workers=1)  # Single thread for minimal contention

# ===== SERIAL AND CONTROLLER MANAGEMENT =====
def flush_serial_port(force=False):
    """Aggressively flush serial port to avoid buffer issues."""
    global last_serial_flush_time
    
    current_time = time.time()
    # Only flush if forced or enough time has passed
    if not force and (current_time - last_serial_flush_time < SERIAL_FLUSH_INTERVAL):
        return True
        
    if not RUNNING_ON_RPI:
        last_serial_flush_time = current_time
        return True

    try:
        # Check if the COM port exists
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            try:
                subprocess.run(["usbreset", COM_PORT], check=False)
                time.sleep(0.2)  # Shorter wait after reset
            except Exception as e:
                logger.error(f"Failed to reset USB: {str(e)}")

            # Check again after reset attempt
            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available after reset")
                return False

        # Ultra-aggressive serial flush with multiple attempts
        with serial.Serial(COM_PORT, 115200, timeout=0.1) as ser:  # Shorter timeout
            # Execute multiple flushes
            for _ in range(3):
                ser.reset_input_buffer()
                ser.reset_output_buffer()

            # Send a harmless command to clear any pending data
            ser.write(b'\r\n')
            # Read and discard any pending data
            _ = ser.read(ser.in_waiting or 1)

        logger.debug(f"Serial port {COM_PORT} flushed successfully")
        last_serial_flush_time = current_time
        return True
    except Exception as e:
        logger.error(f"Error flushing serial port: {str(e)}")
        global serial_error_count
        serial_error_count += 1
        return False

def reset_usb_if_needed():
    """Reset USB connections if we're having serial issues."""
    if not RUNNING_ON_RPI:
        return
        
    global serial_error_count
    
    # Only try reset if we have multiple errors
    if serial_error_count < 3:
        return
        
    try:
        logger.warning("Multiple serial errors - attempting USB reset")
        subprocess.run(["usbreset", COM_PORT], check=False)
        time.sleep(0.5)
        serial_error_count = 0
    except Exception as e:
        logger.error(f"USB reset failed: {str(e)}")

def initialize_xeryon_controller(retry_count=3):
    """Initialize Xeryon controller with comprehensive error handling and retries."""
    global controller, axis, thermal_error_count, amplifier_error_count, serial_error_count

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking Xeryon controller")
        return True

    # Try multiple times with decreasing delay between attempts
    for attempt in range(retry_count):
        try:
            # Different retry behavior based on attempt number
            if attempt > 0:
                logger.info(f"Retrying controller initialization (attempt {attempt+1}/{retry_count})")
                reset_usb_if_needed()
                
            logger.info(f"Initializing Xeryon controller on {COM_PORT}")

            # Aggressively flush the serial port
            if not flush_serial_port(force=True):
                logger.error("Failed to flush serial port - retrying")
                time.sleep(0.2)  # Short delay between attempts
                continue

            # Create controller with shorter timeout
            controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
            axis = controller.addAxis(Stage.XLA_312_3N, "X")
            controller.start()
            time.sleep(0.2)  # Shorter delay for faster startup

            # Configure units and basic parameters - minimize delays between commands
            axis.setUnits(Units.mm)
            axis.sendCommand("POLI=50")  # Set polling rate to maximum

            # Reset error counters
            thermal_error_count = 0
            amplifier_error_count = 0
            serial_error_count = 0

            # Set default parameters with minimal delays
            axis.setSpeed(DEFAULT_SPEED)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            
            # Enable controller
            axis.sendCommand("ENBL=1")
            
            # Home to index
            try:
                axis.findIndex()
            except Exception as e:
                logger.error(f"Error during homing: {str(e)}")
                # Continue anyway - we'll try to operate without homing

            logger.info("Xeryon controller initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Xeryon controller initialization failed (attempt {attempt+1}/{retry_count}): {str(e)}")
            stop_controller()
            
            # Use shorter delays between retries
            delay = 0.5 / (attempt + 1)  # Decreasing delay with each attempt
            time.sleep(delay)

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
            # Send directly without waiting
            axis.sendCommand(f"ACCE={acce_value}")
            logger.info(f"Set acceleration to {acce_value}")

        if dece_value is not None:
            # Ensure dece_value is within valid range (0-65500)
            dece_value = max(0, min(65500, int(dece_value)))
            # Send directly without waiting
            axis.sendCommand(f"DECE={dece_value}")
            logger.info(f"Set deceleration to {dece_value}")

        # Re-enable the controller - critical for thermal protection recovery
        axis.sendCommand("ENBL=1")

        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece parameters: {str(e)}")
        return False

def check_and_recover_from_errors():
    """Check for controller errors and try to recover."""
    global axis, thermal_error_count, amplifier_error_count
    
    if not RUNNING_ON_RPI or not axis:
        return
        
    try:
        # Re-enable the controller - helps recover from thermal protection
        axis.sendCommand("ENBL=1")
        
        # Check error flags if possible
        if hasattr(axis, 'getAMPE'):
            ampe = axis.getAMPE()
            if ampe:
                logger.warning(f"Amplifier error detected (AMPE={ampe})")
                amplifier_error_count += 1
                # Try to recover
                axis.sendCommand("CLRF=1")  # Clear flags
                axis.sendCommand("ENBL=1")  # Re-enable
        
        if hasattr(axis, 'getTPRO'):
            tpro = axis.getTPRO()
            if tpro:
                logger.warning(f"Thermal protection error detected (TPRO={tpro})")
                thermal_error_count += 1
                # Thermal protection needs cooling - we'll just re-enable and hope
                axis.sendCommand("ENBL=1")
                
    except Exception as e:
        logger.error(f"Error checking controller status: {str(e)}")

# ===== CAMERA MANAGEMENT =====
def initialize_camera(retry_count=3):
    """Initialize camera with robust error handling and retries."""
    global picam2, last_camera_flush_time

    # === Adjustable crop settings ===
    CROP_FRACTION = 1 / 3
    HORIZONTAL_SHIFT = 0.0  # -1.0 (left) to 1.0 (right)
    VERTICAL_SHIFT = 0.0  # -1.0 (up) to 1.0 (down)

    # Full sensor resolution for Pi Camera 3 (IMX708)
    SENSOR_WIDTH = 4608
    SENSOR_HEIGHT = 2592

    if not RUNNING_ON_RPI:
        logger.info("Simulation mode: Mocking camera")
        return True

    # Try multiple times with different settings
    for attempt in range(retry_count):
        try:
            if attempt > 0:
                logger.info(f"Retrying camera initialization (attempt {attempt+1}/{retry_count})")
                
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

            # Enable autofocus with fixed exposure for consistent lighting
            picam2.set_controls({
                "AeEnable": False,              # Disable auto exposure
                "AfMode": 2,                    # Continuous autofocus
                "ExposureTime": 20000,          # 20ms = sync with 50Hz lighting
                "AnalogueGain": 1.0             # You can raise this if image too dark
            })        
            
            # Shorter stabilization time to reduce startup delay
            time.sleep(1 if attempt == 0 else 0.5)
            
            # Lock focus after initial autofocus
            picam2.set_controls({"AfMode": 0})  # Lock focus

            # Clear initial frames to get a clean feed
            for _ in range(3):
                _ = picam2.capture_array("main")

            logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
            last_camera_flush_time = time.time()
            return True

        except Exception as e:
            logger.error(f"Camera initialization failed (attempt {attempt+1}/{retry_count}): {str(e)}")
            stop_camera()
            
            # Use shorter delays between retries
            delay = 0.5 / (attempt + 1)  # Decreasing delay with each attempt
            time.sleep(delay)

    return False

def encode_jpeg(frame, quality):
    """Encode a frame as JPEG with minimal processing."""
    encode_param = [
        cv2.IMWRITE_JPEG_QUALITY, quality,
        # Remove OPTIMIZE and PROGRESSIVE flags for faster encoding
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
    """Process incoming commands with ZERO DELAY execution - maximum responsiveness."""
    global axis, last_successful_command_time, current_position
    global thermal_error_count, amplifier_error_count
    
    # Always enable the controller before processing commands
    if RUNNING_ON_RPI and axis:
        try:
            axis.sendCommand("ENBL=1")
        except:
            pass

    # Extract command data
    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")

    # Handle acceleration/deceleration parameters
    acce_value = data.get("acceleration")
    if acce_value is None:
        acce_value = data.get("acce")

    dece_value = data.get("deceleration")
    if dece_value is None:
        dece_value = data.get("dece")

    # Debug log but use shorter format for better performance
    logger.debug(f"Cmd: {command}/{direction}, size:{step_size}{step_unit}")

    response = {"status": "success", "rpiId": STATION_ID}

    try:
        # Handle ping/pong for latency measurements - FAST PATH
        if message_type == "ping":
            # Fast path for ping messages
            return {
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            }
        elif message_type == "pong":
            global last_ping_response_time
            last_ping_response_time = time.time()
            return None
        elif message_type == "heartbeat":
            # Quick heartbeat response
            return {
                "type": "heartbeat_response",
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "rpiId": STATION_ID
            }

        # Verify controller is initialized
        if not RUNNING_ON_RPI or not axis:
            if RUNNING_ON_RPI:
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

        # Almost zero sleep - just enough to yield CPU
        await asyncio.sleep(MIN_SLEEP_DELAY)

        # Handle acceleration and deceleration commands first
        if command in ["acceleration", "acce"]:
            if acce_value is None:
                acce_value = int(direction) if direction.isdigit() else DEFAULT_ACCELERATION
            set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            last_successful_command_time = time.time()
            return response

        elif command in ["deceleration", "dece"]:
            if dece_value is None:
                dece_value = int(direction) if direction.isdigit() else DEFAULT_DECELERATION
            set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            last_successful_command_time = time.time()
            return response

        # Apply acce/dece parameters for all commands if provided
        if acce_value is not None or dece_value is not None:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        # CRITICAL OPTIMIZATION: DIRECT COMMAND EXECUTION
        # Process commands with maximum speed and no waiting
        if command in ["move", "step"]:
            # Validate parameters
            if direction not in ["right", "left"]:
                raise ValueError(f"Invalid direction: {direction}")
            if step_size is None or not isinstance(step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "μm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")

            # Convert to mm
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000

            # Apply direction
            final_step = step_value if direction == "right" else -step_value

            # DIRECT COMMAND EXECUTION: Don't wait for execution
            try:
                # Try to send command without waiting for completion
                if hasattr(axis, 'sendNoWaitCommand'):
                    # Use sendNoWaitCommand if available
                    axis.sendNoWaitCommand(f"STEP={final_step}")
                else:
                    # Otherwise, just use the regular command - still don't wait
                    axis.sendCommand(f"STEP={final_step}")
                
                # Update our tracked position immediately
                with position_lock:
                    current_position += final_step
                    
                # Get current position (doesn't wait for move to complete)
                try:
                    epos = axis.getEPOS()
                except:
                    epos = current_position

                response["message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
                response["step_executed_mm"] = final_step
                response["epos_mm"] = epos
                logger.info(f"Move started: {final_step:.6f} mm toward position: {epos:.6f} mm")
                last_successful_command_time = time.time()
            except Exception as e:
                # Check for specific errors
                error_str = str(e)
                if "amplifier error" in error_str:
                    amplifier_error_count += 1
                    # Try to recover
                    try:
                        axis.sendCommand("ENBL=1")
                        axis.sendCommand("CLRF=1")  # Clear error flags
                    except:
                        pass
                elif "thermal protection" in error_str:
                    thermal_error_count += 1
                    # Try to recover
                    try:
                        axis.sendCommand("ENBL=1")
                    except:
                        pass
                raise

        elif command == "home":
            # DIRECT EXECUTION: Send home command without waiting
            if hasattr(axis, 'sendNoWaitCommand'):
                axis.sendNoWaitCommand("HOME")
            else:
                axis.sendCommand("HOME")
            
            # Get position immediately
            try:
                epos = axis.getEPOS() 
            except:
                epos = 0
            
            # Update tracked position
            with position_lock:
                current_position = epos

            response["message"] = f"Homing started, current EPOS {epos:.6f} mm"
            response["epos_mm"] = epos
            logger.info(f"Homing started, current EPOS: {epos:.6f} mm")
            last_successful_command_time = time.time()

        elif command == "speed":
            speed_value = float(direction)
            # Clamp to reasonable values
            speed_value = max(1, min(1000, speed_value))
            # Set speed directly without waiting
            axis.sendCommand(f"SSPD={speed_value}")
            response["message"] = f"Speed set to {speed_value:.2f} mm/s"
            logger.info(f"Speed set to {speed_value:.2f} mm/s")
            last_successful_command_time = time.time()

        elif command == "scan":
            # Direct scan command without waiting
            if direction == "right":
                if hasattr(axis, 'sendNoWaitCommand'):
                    axis.sendNoWaitCommand("SCAN=1")
                else:
                    axis.sendCommand("SCAN=1")
                response["message"] = "Scanning right started"
            elif direction == "left":
                if hasattr(axis, 'sendNoWaitCommand'):
                    axis.sendNoWaitCommand("SCAN=-1")
                else:
                    axis.sendCommand("SCAN=-1")
                response["message"] = "Scanning left started"
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
                # Immediate stop without waiting
                axis.sendCommand("STOP")
                axis.sendCommand("DPOS=0") 
                response["message"] = "Demo stopped"
                logger.info("Demo stopped")
            else:
                response["message"] = "No demo running"
                logger.info("No demo running - stop request ignored")
            last_successful_command_time = time.time()

        elif command == "stop":
            # Emergency stop - send immediately
            axis.sendCommand("STOP")
            response["message"] = "Emergency stop executed"
            logger.info("Emergency stop executed")
            last_successful_command_time = time.time()

        else:
            response["status"] = "error"
            response["message"] = f"Unknown command: {command}"
            logger.warning(f"Unknown command received: {command}")

        # Check for error conditions and try to recover
        check_and_recover_from_errors()
            
        return response

    except Exception as e:
        logger.error(f"Command processing error: {str(e)}")
        response["status"] = "error"
        response["message"] = f"Error: {str(e)}"
        return response

# ===== DEMO PROGRAM =====
async def run_demo():
    """Run a safe demo sequence that showcases the capabilities of the actuator."""
    global demo_running, axis

    if not RUNNING_ON_RPI:
        logger.info("Demo not available in simulation mode")
        demo_running = False
        return

    logger.info("Starting demo sequence")

    try:
        # Set safe parameters
        set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)

        # Make random moves showing different speeds
        speeds = [100, 250, 500, 750, 1000]
        positions = [-25, -15, -5, 5, 15, 25]  # Positions to move to (in mm)
        move_count = 0
        repeat_count = 0
        last_position = None
        
        # Home first
        axis.findIndex()
        await asyncio.sleep(2.0)
        
        # Main demo loop
        while demo_running and move_count < 50:  # Limit to 50 moves max
            # Bail if demo was stopped
            if not demo_running:
                break
                
            # Choose a random speed
            speed = random.choice(speeds)
            axis.setSpeed(speed)
            
            # Choose a random position, avoiding repeating same position too many times
            position = random.choice(positions)
            if position == last_position:
                repeat_count += 1
                if repeat_count >= 5:  # Maximum 5 repeats of same position
                    # Force a different position
                    other_positions = [p for p in positions if p != position]
                    position = random.choice(other_positions)
                    repeat_count = 0
            else:
                repeat_count = 0
                
            last_position = position
            
            # Get current position for reference
            try:
                current = axis.getEPOS()
            except:
                current = 0
                
            # Make the move directly to position (MOVA=absolute move)
            try:
                logger.info(f"Demo move: to {position:.1f}mm at speed {speed:.1f}mm/s")
                axis.sendCommand(f"MOVA={position}")
                
                # Wait for completion or timeout - but not too long
                wait_start = time.time()
                while time.time() - wait_start < 10:  # Max 10 seconds per move
                    # Check if we need to stop demo
                    if not demo_running:
                        break
                        
                    # Check position for completion
                    try:
                        current = axis.getEPOS()
                        if abs(current - position) < 0.1:  # Within 0.1mm of target
                            break
                    except:
                        pass
                        
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Demo move error: {str(e)}")
                
            # Count the move
            move_count += 1
            
            # Short pause between moves
            await asyncio.sleep(0.5)
                
        # End demo - return to zero
        if demo_running:
            try:
                logger.info("Demo complete - returning to zero")
                axis.sendCommand("MOVA=0")
            except:
                pass
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        demo_running = False
        logger.info("Demo sequence ended")

# ===== CAMERA PROCESSING =====
async def send_camera_frames(websocket):
    """Send camera frames with absolutely zero lag and immediate movement feedback."""
    global picam2, last_successful_frame_time, axis, last_camera_flush_time, last_frame_count
    
    # Frame tracking
    frame_count = 0
    
    # Command detection for ultra-responsive camera
    command_active = False
    last_command_check = 0
    
    logger.info("Starting zero-lag camera frame sender")
    
    # Main camera loop - optimized for maximum performance
    while not shutdown_requested:
        try:
            # Skip simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue
                
            # Initialize camera if needed
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                initialize_camera()
                await asyncio.sleep(0.5)
                continue
                
            # CRITICAL: Absolute minimal sleep for maximum responsiveness
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
            # Check for recent commands every millisecond
            current_time = time.time()
            if current_time - last_command_check >= 0.001:
                command_active = (current_time - last_successful_command_time < 0.5)  # 500ms window
                last_command_check = current_time
                
            # CRITICAL: Flush buffer during active commands
            if command_active:
                try:
                    # Ultra-aggressive buffer flushing during commands
                    for _ in range(5):  # Discard 5 frames to get newest image
                        _ = picam2.capture_array("main")
                    last_camera_flush_time = current_time
                except Exception as e:
                    logger.error(f"Command buffer flush error: {e}")
            
            # CRITICAL: Periodically flush camera buffer even during idle 
            if current_time - last_camera_flush_time >= CAMERA_FLUSH_INTERVAL:
                try:
                    # Just capture and discard one frame during idle periods
                    _ = picam2.capture_array("main")
                    last_camera_flush_time = current_time
                except Exception as e:
                    pass
            
            # Capture the newest possible frame
            try:
                # This must be the absolute freshest frame
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # Always add frame number text
            frame_text = f"Frame: {frame_count}"
            cv2.putText(frame, frame_text, (10, 30), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                      
            # Optimize encoding quality based on command status
            try:
                # Lower quality during commands for faster transmission
                quality = 30 if command_active else JPEG_QUALITY
                
                # Direct encoding - no async for minimal latency
                buffer = encode_jpeg(frame, quality)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
            
            # Always include current position data for real-time display
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    # Get position directly, no waiting
                    epos = axis.getEPOS()
                    position_data = epos
                    with position_lock:
                        current_position = epos
                except:
                    pass
            
            # Prepare the message with timestamp for plotting
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Include position data when available
            if position_data is not None:
                frame_data["epos"] = position_data
            
            # Send the frame with no timeout (compatible with all websocket versions)
            try:
                # Direct send without timeout for compatibility with all ws libraries
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_frame_count = frame_count
                last_successful_frame_time = time.time()
            except Exception as e:
                logger.error(f"Frame send error: {e}")
                break  # Exit to reconnect
                
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)

# ===== POSITION UPDATE SENDER =====
async def send_position_updates(websocket):
    """Send position updates at maximum frequency for responsive visualization."""
    global axis, current_position
    
    logger.info("Starting high-speed position update sender")
    update_count = 0
    last_update_time = time.time()
    
    while not shutdown_requested:
        try:
            # Skip if not on RPi
            if not RUNNING_ON_RPI:
                await asyncio.sleep(POSITION_UPDATE_INTERVAL)
                continue
                
            # Use absolute minimum sleep for maximum update frequency
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
            # Throttle updates to avoid flooding
            current_time = time.time()
            if current_time - last_update_time < POSITION_UPDATE_INTERVAL:
                continue
                
            # Reset update time
            last_update_time = current_time
            
            # Check if controller is ready
            if not axis:
                await asyncio.sleep(0.1)
                continue
            
            # Get the current position - directly with no waiting
            try:
                epos = axis.getEPOS()
                with position_lock:
                    current_position = epos
            except Exception as e:
                logger.error(f"Position read error: {e}")
                await asyncio.sleep(0.1)
                continue
            
            # Prepare update with accurate timestamp for graph
            position_update = {
                "type": "position_update",
                "rpiId": STATION_ID,
                "epos": epos,
                "timestamp": datetime.now().isoformat()
            }
            
            # Send with no timeout - compatible with all websockets
            try:
                await websocket.send(json.dumps(position_update))
                update_count += 1
            except Exception as e:
                logger.error(f"Position update send error: {e}")
                break  # Connection likely dead, exit to trigger reconnection
            
        except Exception as e:
            logger.error(f"Position sender error: {str(e)}")
            await asyncio.sleep(0.1)
    
    logger.info("Position update sender stopping")

# ===== HEALTH MONITORING =====
async def health_checker(websocket):
    """Monitor and report on system health with ultra-reliable connection checking."""
    global shutdown_requested, thermal_error_count, amplifier_error_count
    
    logger.info(f"Starting health checker (interval={HEARTBEAT_INTERVAL}s)")
    last_health_check = time.time()
    
    while not shutdown_requested:
        try:
            # Only run health check at specified interval
            current_time = time.time()
            if current_time - last_health_check < HEARTBEAT_INTERVAL:
                await asyncio.sleep(MIN_SLEEP_DELAY)
                continue
                
            # Reset health check time
            last_health_check = current_time
            
            # Gather health metrics
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            ping_silence = current_time - last_ping_response_time
            uptime = current_time - startup_time

            # Send health ping with minimal size
            try:
                # Create minimal health data
                health_data = {
                    "type": "health_check",
                    "timestamp": datetime.now().isoformat(),
                    "rpiId": STATION_ID,
                    "uptime": int(uptime),
                    "errors": {
                        "thermal": thermal_error_count,
                        "amplifier": amplifier_error_count,
                        "serial": serial_error_count
                    }
                }
                
                # Send without timeout (compatible with all websocket versions)
                await websocket.send(json.dumps(health_data))
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
                # Connection is likely dead
                break

            # Check if we need to flush serial port
            if current_time - last_serial_flush_time >= SERIAL_FLUSH_INTERVAL:
                flush_serial_port()
            
            # Detect silent camera - if 30s without frames, try to restart it
            if frame_silence > 30 and RUNNING_ON_RPI and picam2:
                logger.warning(f"Frame silence detected: {frame_silence:.1f}s - restarting camera")
                try:
                    stop_camera()
                    await asyncio.sleep(0.5)
                    initialize_camera()
                except Exception as e:
                    logger.error(f"Failed to reset camera: {str(e)}")
            
            # Send ping to verify connection health
            try:
                ping_data = {
                    "type": "ping",
                    "timestamp": datetime.now().isoformat(),
                    "rpiId": STATION_ID,
                    "uptime": int(uptime)
                }
                
                # Send ping without timeout (compatible with all ws versions)
                await websocket.send(json.dumps(ping_data))
                
            except Exception as e:
                logger.error(f"Error sending ping: {str(e)}")
                # Connection is probably dead
                break
            
            # Check for and recover from errors
            check_and_recover_from_errors()
            
        except Exception as e:
            logger.error(f"Health checker error: {str(e)}")
            await asyncio.sleep(0.5)
    
    logger.info("Health checker stopping")

# ===== MAIN CLIENT FUNCTION =====
async def rpi_client():
    """Main client function with ultra-reliable connection handling."""
    global shutdown_requested, reconnect_delay, total_connection_failures
    global startup_time, demo_running
    
    startup_time = time.time()
    logger.info(f"Starting Ultra-Optimized RPi Client for {STATION_ID}")
    logger.info(f"Connecting to server: {SERVER_URL}")
    logger.info(f"Ultra-responsive mode enabled with {MIN_SLEEP_DELAY*1000000:.2f}μs minimum delay")
    
    # Initialize hardware with retry logic
    if RUNNING_ON_RPI:
        logger.info("Initializing hardware...")
        initialize_camera()
        initialize_xeryon_controller()
    
    # Main connection loop
    while not shutdown_requested:
        try:
            # Generate unique connection ID for tracking
            connection_id = f"{int(time.time())}"
            
            # Log connection attempt
            logger.info(f"Connecting to {SERVER_URL} (attempt {total_connection_failures+1}, ID: {connection_id})")
            
            # Connect with basic parameters - compatible with all websocket versions
            async with websockets.connect(
                    SERVER_URL,
                    # Disable ping/pong mechanism - we'll implement our own
                    ping_interval=None,
                    ping_timeout=None
            ) as websocket:
                logger.info("WebSocket connection established")
                
                # Register this connection immediately
                registration_message = {
                    "type": "register",
                    "rpiId": STATION_ID,
                    "connectionType": "combined",  # Single connection for both camera and control
                    "status": "ready",
                    "message": f"RPi {STATION_ID} connected (Ultra-Optimized Client)",
                    "connectionId": connection_id,
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(registration_message))
                logger.info(f"Sent registration message for {STATION_ID}")
                
                # Start background tasks
                frame_task = asyncio.create_task(send_camera_frames(websocket))
                await asyncio.sleep(MIN_SLEEP_DELAY)  # Minimal delay to avoid task contention
                
                position_task = asyncio.create_task(send_position_updates(websocket))
                await asyncio.sleep(MIN_SLEEP_DELAY)  # Minimal delay to avoid task contention
                
                health_task = asyncio.create_task(health_checker(websocket))
                
                # Reset connection tracking
                total_connection_failures = 0
                reconnect_delay = RECONNECT_BASE_DELAY
                
                # Handle incoming messages with manual timeout
                try:
                    while not shutdown_requested:
                        # Use a manual timeout implementation that works with any ws version
                        message_received = False
                        message = None
                        
                        # Use a task for timeout
                        recv_task = asyncio.create_task(websocket.recv())
                        timeout_task = asyncio.create_task(asyncio.sleep(10))  # 10 second timeout
                        
                        # Wait for either the message or the timeout
                        done, pending = await asyncio.wait(
                            {recv_task, timeout_task},
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            
                        # Check if we got a message
                        if recv_task in done:
                            try:
                                message = recv_task.result()
                                message_received = True
                            except Exception as e:
                                logger.error(f"Error receiving message: {e}")
                                break
                        else:
                            # Timeout occurred - send ping to check connection
                            try:
                                ping_data = {
                                    "type": "ping",
                                    "timestamp": datetime.now().isoformat(),
                                    "rpiId": STATION_ID
                                }
                                await websocket.send(json.dumps(ping_data))
                                logger.debug("Ping sent during recv timeout - connection still active")
                                continue
                            except Exception as e:
                                logger.error(f"Connection dead (ping failed): {e}")
                                break
                        
                        # Process the received message
                        if message_received and message:
                            # Absolute minimal delay to prevent CPU hogging
                            await asyncio.sleep(MIN_SLEEP_DELAY)
                            
                            try:
                                data = json.loads(message)
                                
                                if data.get("type") == "command":
                                    # Process command and send response directly
                                    response = await process_command(data)
                                    if response:
                                        # Send response directly for faster handling
                                        await websocket.send(json.dumps(response))
                                
                                elif data.get("type") == "ping":
                                    # Handle ping messages for latency measurement
                                    response = {
                                        "type": "pong",
                                        "timestamp": data.get("timestamp"),
                                        "rpiId": STATION_ID
                                    }
                                    await websocket.send(json.dumps(response))
                                
                            except json.JSONDecodeError as e:
                                logger.error(f"Invalid JSON received: {e}")
                            except Exception as e:
                                logger.error(f"Error processing message: {str(e)}")
                                await asyncio.sleep(0.01)
                            
                except websockets.exceptions.ConnectionClosed as e:
                    logger.error(f"WebSocket connection closed: {e}")
                except Exception as e:
                    logger.error(f"Message handling error: {e}")
                
                # Connection lost, clean up tasks
                for task in [frame_task, position_task, health_task]:
                    if not task.done():
                        task.cancel()
                
                try:
                    # Wait for tasks to complete or cancel
                    await asyncio.gather(frame_task, position_task, health_task, return_exceptions=True)
                except asyncio.CancelledError:
                    pass
                
                logger.info("Background tasks stopped, will reconnect")
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            
            # Ultra-fast reconnection with minimal delay
            total_connection_failures += 1
            
            # Use ultra-aggressive reconnection delay
            if "device not connected" in str(e).lower() or "cannot connect" in str(e).lower():
                # For connection refusals, retry almost immediately
                actual_delay = 0.05  # 50ms retry for connection refusals
                logger.warning(f"Connection refused - retrying in {actual_delay:.2f}s")
            else:
                # For other errors, use very short delay
                reconnect_delay = min(MAX_RECONNECT_DELAY, 
                                    RECONNECT_BASE_DELAY * (1.1 ** min(total_connection_failures % 3, 2)))
                
                # Add minimal jitter (0-10%)
                jitter = random.uniform(0, 0.1 * reconnect_delay)
                actual_delay = reconnect_delay + jitter
            
            logger.info(f"Reconnecting in {actual_delay:.2f}s (attempt {total_connection_failures})...")
            
            # For first few attempts, use even more aggressive retry
            if total_connection_failures < 5:
                actual_delay = min(0.05, actual_delay)  # Almost immediate retry for first 5 attempts
                
            await asyncio.sleep(actual_delay)
            
            # Reset hardware after multiple failures
            if total_connection_failures % 5 == 0:
                logger.warning(f"Multiple connection failures ({total_connection_failures}), resetting hardware...")
                
                # Stop hardware
                if RUNNING_ON_RPI:
                    stop_camera()
                    stop_controller()
                
                # Reset demo state
                demo_running = False
                
                # Short delay before reinitializing (200ms)
                await asyncio.sleep(0.2)
                
                # Reinitialize hardware
                if RUNNING_ON_RPI:
                    initialize_camera()
                    initialize_xeryon_controller()

# ===== ENTRY POINT =====
async def main():
    """Entry point with proper signal handling and cleanup."""
    global shutdown_requested
    
    # Set up signal handlers
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
    
    # Stop hardware
    if RUNNING_ON_RPI:
        stop_camera()
        stop_controller()
    
    # Force garbage collection
    gc.collect()
    logger.info("Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        # Attempt emergency hardware shutdown
        if RUNNING_ON_RPI:
            try:
                if 'picam2' in globals() and picam2:
                    stop_camera()
                if 'controller' in globals() and controller:
                    stop_controller()
            except:
                pass