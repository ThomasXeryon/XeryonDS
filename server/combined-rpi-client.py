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
from picamera2 import Picamera2
from websockets.exceptions import ConnectionClosed
import serial
from datetime import datetime
from collections import deque

# Add Xeryon library path
sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
from Xeryon import Xeryon, Stage, Units

# Set up logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1920
RESOLUTION_HEIGHT = 1080
JPEG_QUALITY = 50
TARGET_FPS = 30
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1

# Acceleration and deceleration defaults
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750

# CPU Usage Management
CPU_MONITOR_INTERVAL = 10  # seconds
MIN_SLEEP_DELAY = 0.001  # 1ms minimum delay between operations

# Globals
picam2 = None
controller = None
axis = None
demo_running = False
shutdown_requested = False
command_queue = asyncio.Queue()
reconnect_delay = 1
max_reconnect_delay = 30

# Error handling and health check
health_check_interval = 5  # seconds
total_connection_failures = 0
max_failures_before_reset = 5
last_successful_command_time = time.time()
last_successful_frame_time = time.time()
last_ping_response_time = time.time()


# Function to set acceleration and deceleration parameters
def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration parameters."""
    global axis
    if not axis:
        logger.error("Cannot set acce/dece: Axis not initialized")
        return False

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

        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece: {str(e)}")
        return False


# Camera Functions
def initialize_camera():
    """Initialize camera with retry logic."""
    global picam2
    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={
                "size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT),
                "format": "RGB888"
            })
        picam2.configure(config)
        picam2.start()
        logger.info(
            f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        time.sleep(1)
        return True
    except Exception as e:
        logger.error(f"Camera init failed: {str(e)}")
        stop_camera(picam2)
        picam2 = None
        gc.collect()
        return False


def stop_camera(cam):
    """Safely stop and close camera."""
    try:
        if cam:
            if hasattr(cam, 'started') and cam.started:
                cam.stop()
                logger.info("Camera stopped")
            try:
                cam.close()
                logger.info("Camera closed")
            except Exception as e:
                logger.warning(f"Camera close failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error stopping camera: {str(e)}")
    finally:
        gc.collect()


# Xeryon Functions
def initialize_xeryon_controller():
    """Initialize Xeryon with robust serial retry."""
    global controller, axis
    try:
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not foundâattempting USB reset")
            subprocess.run(["usbreset", COM_PORT], check=False)
            time.sleep(1)
            if not os.path.exists(COM_PORT):
                raise serial.SerialException(f"{COM_PORT} still missing")

        logger.info(f"Initializing Xeryon on {COM_PORT}")
        with serial.Serial(COM_PORT, 115200, timeout=1) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()

        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.findIndex()

        # Set default speed, acceleration, and deceleration
        base_speed = 500
        axis.setSpeed(base_speed)
        set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)

        logger.info(f"Xeryon initialized with default parameters")
        return True
    except Exception as e:
        logger.error(f"Xeryon init failed: {str(e)}")
        if controller:
            stop_controller(controller)
            controller = None
            axis = None
        return False


def stop_controller(ctrl):
    """Safely stop Xeryon."""
    try:
        if ctrl:
            ctrl.stop()
            logger.info("Controller stopped")
    except Exception as e:
        logger.error(f"Error stopping controller: {str(e)}")


async def run_demo():
    """Run an exciting Xeryon demo with dynamic movement patterns."""
    global demo_running, axis
    demo_running = True
    logger.info("Demo started")
    
    # Get current position to understand limits
    try:
        current_pos = await asyncio.to_thread(axis.getEPOS)
        logger.info(f"Starting demo at position: {current_pos:.3f} mm")
    except Exception as e:
        logger.error(f"Error getting position: {str(e)}")
        current_pos = 0.0
    
    # Demo sequence tracker
    sequence_num = 0
    
    # Function to check if demo should still run
    def should_continue():
        return demo_running and axis
        
    try:
        # SEQUENCE 1: Fast micro-steps with increasing amplitude
        if should_continue():
            logger.info("Demo Sequence 1: Precision micro-steps with increasing amplitude")
            await asyncio.to_thread(axis.setSpeed, 150)
            # Set medium acceleration/deceleration for precise movements
            set_acce_dece_params(20000, 20000)
            
            # Start with tiny steps that gradually get larger
            step_sizes = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5]
            for step_size in step_sizes:
                if not should_continue(): break
                direction = 1 if current_pos < 7.5 else -1  # Ensure we stay in safe range
                await asyncio.to_thread(axis.step, step_size * direction)
                current_pos += step_size * direction
                logger.info(f"Demo: Micro-step {step_size * direction:.3f} mm")
                await asyncio.sleep(0.2)  # Quick succession of steps
            
        # SEQUENCE 2: Rapid oscillations around a point
        if should_continue():
            logger.info("Demo Sequence 2: Rapid oscillations")
            # Set high speed and acceleration for snappy movement
            await asyncio.to_thread(axis.setSpeed, 600)
            set_acce_dece_params(45000, 45000)
            
            # Execute rapid back-and-forth movements
            oscillation_sizes = [0.5, 0.8, 1.0, 0.8, 0.5, 0.3]
            for size in oscillation_sizes:
                if not should_continue(): break
                for _ in range(2):  # Two oscillations at each size
                    if not should_continue(): break
                    # Step right
                    await asyncio.to_thread(axis.step, size)
                    current_pos += size
                    await asyncio.sleep(0.1)
                    # Step left
                    await asyncio.to_thread(axis.step, -size)
                    current_pos -= size
                    await asyncio.sleep(0.1)
            
        # SEQUENCE 3: Long scan followed by precise positioning
        if should_continue():
            logger.info("Demo Sequence 3: Long scan with precision stop")
            # Move to left side first if needed
            if current_pos > 7.0:
                await asyncio.to_thread(axis.setSpeed, 400)
                set_acce_dece_params(30000, 30000)
                await asyncio.to_thread(axis.step, -5.0)
                current_pos -= 5.0
                await asyncio.sleep(0.3)
            
            # Set up for scan
            await asyncio.to_thread(axis.setSpeed, 200)
            set_acce_dece_params(15000, 40000)  # Low accel, high decel for dramatic stop
            
            # Start scan right
            await asyncio.to_thread(axis.startScan, 1)
            logger.info("Demo: Starting long scan right")
            await asyncio.sleep(2.0)  # Let it scan for a while
            await asyncio.to_thread(axis.stopScan)
            logger.info("Demo: Scan stopped dramatically")
            
            # Get new position
            try:
                current_pos = await asyncio.to_thread(axis.getEPOS)
                logger.info(f"Current position after scan: {current_pos:.3f} mm")
            except Exception as e:
                logger.error(f"Error getting position: {str(e)}")
            
            await asyncio.sleep(0.5)  # Pause for effect
        
        # SEQUENCE 4: Precise rapid step sequence
        if should_continue():
            logger.info("Demo Sequence 4: Rapid precise steps")
            # Set medium-high speed with balanced acceleration
            await asyncio.to_thread(axis.setSpeed, 350)
            set_acce_dece_params(35000, 35000)
            
            # Create an interesting pattern - 10 steps in rapid succession
            step_pattern = [0.2, 0.3, 0.4, 0.3, 0.2, -0.2, -0.3, -0.4, -0.3, -0.2]
            for step in step_pattern:
                if not should_continue(): break
                await asyncio.to_thread(axis.step, step)
                current_pos += step
                logger.info(f"Demo: Quick step {step:.2f} mm")
                await asyncio.sleep(0.15)  # Very rapid succession
            
            await asyncio.sleep(0.5)  # Short pause after the sequence
        
        # SEQUENCE 5: Slow, precise movement with varying acceleration
        if should_continue():
            logger.info("Demo Sequence 5: Slow movement with variable acceleration")
            # First determine which direction has more room
            direction = -1 if current_pos > 7.5 else 1
            
            # Set slow speed for dramatic effect
            await asyncio.to_thread(axis.setSpeed, 50)
            
            # Start with extremely low acceleration for a slow start
            set_acce_dece_params(2000, 50000)
            await asyncio.to_thread(axis.step, 2.0 * direction)
            current_pos += 2.0 * direction
            logger.info(f"Demo: Slow dramatic move with 2.0 mm {direction}")
            await asyncio.sleep(0.3)
            
            # Then sudden high acceleration for contrast
            set_acce_dece_params(60000, 60000)
            await asyncio.to_thread(axis.step, -1.5 * direction)
            current_pos -= 1.5 * direction
            logger.info(f"Demo: Quick snap back with -1.5 mm {-direction}")
            await asyncio.sleep(0.5)
        
        # SEQUENCE 6: Alternating scan directions with varying speeds
        if should_continue():
            logger.info("Demo Sequence 6: Alternating scans with varying speeds")
            
            # First scan right at medium speed
            await asyncio.to_thread(axis.setSpeed, 250)
            set_acce_dece_params(25000, 25000)
            await asyncio.to_thread(axis.startScan, 1)
            logger.info("Demo: Medium speed scan right")
            await asyncio.sleep(1.0)
            await asyncio.to_thread(axis.stopScan)
            
            # Short delay
            await asyncio.sleep(0.3)
            
            # Then scan left at high speed
            await asyncio.to_thread(axis.setSpeed, 700)
            set_acce_dece_params(55000, 55000)
            await asyncio.to_thread(axis.startScan, -1)
            logger.info("Demo: High speed scan left")
            await asyncio.sleep(0.8)
            await asyncio.to_thread(axis.stopScan)
            
            # Get updated position
            try:
                current_pos = await asyncio.to_thread(axis.getEPOS)
                logger.info(f"Current position after scans: {current_pos:.3f} mm")
            except Exception as e:
                logger.error(f"Error getting position: {str(e)}")
        
        # FINALE: Return to home with smooth movement
        if should_continue():
            logger.info("Demo Finale: Returning to home position")
            await asyncio.to_thread(axis.setSpeed, 300)
            set_acce_dece_params(20000, 20000)
            
            # Home the axis
            await asyncio.to_thread(axis.findIndex)
            logger.info("Demo: Homed to index position")
            
            # Set default parameters for clean finish
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            
        logger.info("Demo sequence completed successfully")
        
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        # Always restore default parameters
        try:
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            await asyncio.to_thread(axis.setSpeed, 500)  # Restore default speed
        except Exception as e:
            logger.error(f"Error restoring default parameters: {str(e)}")
        
        demo_running = False
        logger.info("Demo stopped")


async def process_command(data):
    """Handle Xeryon commands and pings."""
    global demo_running, axis, last_successful_command_time

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")

    # Handle both old and new parameter names for acceleration and deceleration
    acce_value = data.get("acceleration")
    if acce_value is None:
        acce_value = data.get("acce")

    dece_value = data.get("deceleration")
    if dece_value is None:
        dece_value = data.get("dece")

    logger.debug(
        f"COMMAND RECEIVED: {command}, acce: {acce_value}, dece: {dece_value}")

    response = {"status": "success", "rpiId": STATION_ID}

    try:
        # Handle ping/pong messages for latency measurements
        if message_type == "ping":
            response.update({
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            })
            logger.debug(f"Replied to ping, timestamp: {timestamp}")
            return response
        elif message_type == "pong":
            global last_ping_response_time
            last_ping_response_time = time.time()
            logger.debug(f"Received pong, timestamp: {timestamp}")
            return None
        elif message_type == "heartbeat":
            # Special heartbeat message
            response.update({
                "type": "heartbeat_response",
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "rpiId": STATION_ID
            })
            return response

        if not axis:
            raise Exception("Axis not initializedâcannot process command")

        response["message"] = f"Executing command '{command}'"
        logger.info(
            f"Processing command: {command}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}, acce: {acce_value}, dece: {dece_value}"
        )

        # Add small sleep to reduce CPU usage
        await asyncio.sleep(MIN_SLEEP_DELAY)

        # Handle acceleration and deceleration commands directly
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

        # Set acce/dece parameters for all commands if provided
        if acce_value is not None or dece_value is not None:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value is not None:
                response["acceleration"] = acce_value
            if dece_value is not None:
                response["deceleration"] = dece_value

        if command in ["move", "step"]:
            if direction not in ["right", "left"]:
                raise ValueError(f"Invalid direction: {direction}")
            if step_size is None or not isinstance(
                    step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "Âµm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")
            step_value = float(step_size)
            if step_unit == "Âµm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
            final_step = step_value if direction == "right" else -step_value
            await asyncio.to_thread(axis.step, final_step)
            response[
                "message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
            response["step_executed_mm"] = final_step
            logger.info(f"Move executed: {final_step:.6f} mm")
            last_successful_command_time = time.time()

        elif command == "home":
            await asyncio.to_thread(axis.findIndex)
            epos = await asyncio.to_thread(axis.getEPOS)
            response["message"] = f"Homed to index, EPOS {epos:.6f} mm"
            response["epos_mm"] = epos
            logger.info(f"Homed, EPOS: {epos:.6f} mm")
            last_successful_command_time = time.time()

        elif command == "speed":
            speed_value = float(direction)
            await asyncio.to_thread(axis.setSpeed, speed_value)
            response["message"] = f"Speed set to {speed_value:.2f} mm/s"
            logger.info(f"Speed set: {speed_value:.2f} mm/s")
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
            logger.info(f"Scan started: {direction}")
            last_successful_command_time = time.time()

        elif command == "demo_start":
            if not demo_running:
                asyncio.create_task(run_demo())
                response["message"] = "Demo started"
                logger.info("Demo started")
            else:
                response["message"] = "Demo already running"
                logger.info("Demo already running")
            last_successful_command_time = time.time()

        elif command == "demo_stop":
            if demo_running:
                demo_running = False
                await asyncio.to_thread(axis.stopScan)
                await asyncio.to_thread(axis.setDPOS, 0)
                response["message"] = "Demo stopped, DPOS 0 mm"
                logger.info("Demo stopped, DPOS 0 mm")
            else:
                response["message"] = "No demo running"
                logger.info("No demo running")
            last_successful_command_time = time.time()

        elif command == "stop":
            await asyncio.to_thread(axis.stopScan)
            await asyncio.to_thread(axis.setDPOS, 0)
            response["message"] = "Stopped, DPOS 0 mm"
            logger.info("Stopped, DPOS 0 mm")
            last_successful_command_time = time.time()

        elif command == "reset_params":
            # Reset to default parameters
            await asyncio.to_thread(axis.setSpeed, 500)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            response["message"] = f"Parameters reset to defaults"
            logger.info(f"Parameters reset to defaults")
            last_successful_command_time = time.time()

        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        response["status"] = "error"
        response["message"] = f"Command '{command}' failed: {str(e)}"
        logger.error(f"Command error: {str(e)}")

    # Add another small sleep to reduce CPU usage before returning
    await asyncio.sleep(MIN_SLEEP_DELAY)
    return response


async def send_camera_frames(websocket):
    """Send camera frames in a background task."""
    global picam2, last_successful_frame_time

    frame_count = 0
    last_frame_time = time.time()

    while not shutdown_requested:
        try:
            if not picam2 or not hasattr(picam2,
                                         'started') or not picam2.started:
                logger.error("Camera not started, pausing frame sending")
                await asyncio.sleep(1)
                continue

            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time

            # Rate limit frame sending to target FPS
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)

            # Add small delay to reduce CPU usage
            await asyncio.sleep(MIN_SLEEP_DELAY)

            last_frame_time = time.time()
            rgb_buffer = picam2.capture_array("main")
            frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)

            # Get timestamp for this frame
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # Add ID number and timestamp to frame
            id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
            cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)

            # Encode and compress the frame
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')

            # Add another small sleep after encoding to reduce CPU load
            await asyncio.sleep(MIN_SLEEP_DELAY)

            # Create and send the frame data
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": jpg_as_text,
                "timestamp": frame_time,
                "frameNumber": frame_count
            }

            try:
                await websocket.send(json.dumps(frame_data))
                # Increment frame count
                frame_count += 1
                last_successful_frame_time = time.time()

                # Log frame info (reduce verbosity for production)
                if frame_count % 10 == 0:  # Log only every 10 frames
                    logger.debug(f"Sent frame {frame_count} at {frame_time}")
            except Exception as e:
                logger.error(f"Failed to send frame: {e}")
                # Sleep to allow for connection recovery
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Camera frame sending error: {str(e)}")
            # Sleep longer on error to prevent CPU spikes
            await asyncio.sleep(2)

        # Add a small delay at the end of each loop iteration
        await asyncio.sleep(MIN_SLEEP_DELAY)


async def send_position_updates(websocket):
    """Send position updates in a background task."""
    global axis, last_successful_command_time

    last_epos = None
    last_update_time = time.time()

    while not shutdown_requested:
        try:
            if not axis:
                logger.warning(
                    "Axis not initialized, pausing position updates")
                await asyncio.sleep(1)
                continue

            # Only send position updates at specified interval
            current_time = time.time()
            elapsed = current_time - last_update_time

            if elapsed < EPOS_UPDATE_INTERVAL:
                # Sleep for the remaining time to reach the desired update interval
                await asyncio.sleep(EPOS_UPDATE_INTERVAL - elapsed +
                                    MIN_SLEEP_DELAY)

            last_update_time = time.time()

            # Get current position
            epos = await asyncio.to_thread(axis.getEPOS)

            # Only send if position changed or every 1 second regardless
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

                    # Log position (reduce verbosity for production)
                    logger.debug(f"Position update: {epos:.6f} mm")
                except Exception as e:
                    logger.error(f"Failed to send position update: {e}")
                    await asyncio.sleep(0.5)

            # Add small delay to reduce CPU usage
            await asyncio.sleep(MIN_SLEEP_DELAY)

        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            await asyncio.sleep(1)

        # Add a small delay at the end of each loop iteration
        await asyncio.sleep(MIN_SLEEP_DELAY)


async def health_checker(websocket):
    """Actively check connection health."""
    global startup_time

    while not shutdown_requested:
        try:
            # Check if we need system restart
            current_time = time.time()
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            ping_silence = current_time - last_ping_response_time

            # Log the health status
            logger.debug(
                f"Health: command={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s"
            )

            # Add small delay to reduce CPU usage
            await asyncio.sleep(MIN_SLEEP_DELAY)

            # Send a health check ping
            ping_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID,
                "uptime": time.time() - startup_time
            }

            try:
                await websocket.send(json.dumps(ping_data))
            except Exception as e:
                logger.error(f"Failed to send health check: {e}")

            # Wait before next health check
            await asyncio.sleep(health_check_interval)

        except Exception as e:
            logger.error(f"Health checker error: {str(e)}")
            await asyncio.sleep(1)


async def monitor_cpu_usage():
    """Monitor CPU usage periodically, adjust delays if needed."""
    while not shutdown_requested:
        try:
            # In a real implementation we would check actual CPU usage
            # For now we just log the monitoring activity
            logger.info(
                "CPU monitoring active - preventing high CPU usage with sleep intervals"
            )

            # Check if system is running hot by reading temperature
            try:
                # Read temperature on Raspberry Pi
                temp_output = subprocess.check_output(
                    ['vcgencmd', 'measure_temp']).decode()
                temp = float(
                    temp_output.replace('temp=', '').replace('\'C', ''))

                if temp > 70:  # Temperature threshold
                    logger.warning(
                        f"System running hot: {temp}Â°C - adding extra cooling delays"
                    )
                    # Increase all minimum delays temporarily
                    global MIN_SLEEP_DELAY
                    old_delay = MIN_SLEEP_DELAY
                    MIN_SLEEP_DELAY = 0.01  # 10ms when hot
                    await asyncio.sleep(30)  # Apply for 30 seconds
                    MIN_SLEEP_DELAY = old_delay
            except Exception as e:
                logger.error(f"Failed to check temperature: {e}")

            # Wait before checking again
            await asyncio.sleep(CPU_MONITOR_INTERVAL)

        except Exception as e:
            logger.error(f"CPU monitoring error: {e}")
            await asyncio.sleep(5)  # Sleep longer on error


async def command_processor():
    """Process queued commands in background."""
    while not shutdown_requested:
        try:
            # Add a small delay at start of each loop to prevent CPU hogging
            await asyncio.sleep(MIN_SLEEP_DELAY)

            command = await command_queue.get()

            # Add to websocket outgoing queue
            current_websocket = getattr(command_processor, 'websocket', None)
            if current_websocket:
                try:
                    await current_websocket.send(json.dumps(command))
                    logger.debug(
                        f"Sent queued command: {command.get('type')} {command.get('command', '')}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send queued command: {str(e)}")
                    # Put command back in queue
                    await command_queue.put(command)

            # Let other tasks run
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Command processor error: {str(e)}")
            await asyncio.sleep(1)


async def rpi_client():
    """Main function to run the RPI client with a single WebSocket connection."""
    global shutdown_requested, reconnect_delay, total_connection_failures
    global startup_time

    startup_time = time.time()

    # Start the CPU monitoring task
    #cpu_monitor_task = asyncio.create_task(monitor_cpu_usage())

    # Start the command processor task
    cmd_processor_task = asyncio.create_task(command_processor())

    # Initialize hardware
    logger.info(f"Starting RPi Client for {STATION_ID}")
    logger.info(f"Connecting to server: {SERVER_URL}")
    logger.info(
        f"CPU usage optimization enabled with {MIN_SLEEP_DELAY*1000:.2f}ms minimum delays"
    )

    # Initialize hardware - with one retry if needed
    logger.info("Initializing camera...")
    if not initialize_camera():
        logger.warning("First camera init failed, retrying once...")
        await asyncio.sleep(2)
        initialize_camera()

    logger.info("Initializing Xeryon controller...")
    if not initialize_xeryon_controller():
        logger.warning("First Xeryon init failed, retrying once...")
        await asyncio.sleep(2)
        initialize_xeryon_controller()

    connection_id = f"single_{int(time.time())}"

    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL}...")

            # Connect to WebSocket server
            websocket = await websockets.connect(
                SERVER_URL,
                ping_interval=None,  # Disable automatic ping/pong
                close_timeout=5)

            logger.info("WebSocket connection established")

            # Register this connection
            registration_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType":
                "combined",  # Single connection for both camera and control
                "status": "ready",
                "message": f"RPi {STATION_ID} combined connection initialized",
                "connectionId": connection_id,
                "timestamp": datetime.now().isoformat()
            }

            # Send registration message
            await websocket.send(json.dumps(registration_message))
            logger.info(f"Sent registration message: {registration_message}")

            # Store the websocket in command processor
            command_processor.websocket = websocket

            # Start background tasks
            frame_task = asyncio.create_task(send_camera_frames(websocket))
            position_task = asyncio.create_task(
                send_position_updates(websocket))
            health_task = asyncio.create_task(health_checker(websocket))

            # Reset connection failures and delay
            total_connection_failures = 0
            reconnect_delay = 1

            # Handle incoming messages in this task
            try:
                while not shutdown_requested:
                    message = await websocket.recv()

                    # Add small delay to reduce CPU usage
                    await asyncio.sleep(MIN_SLEEP_DELAY)

                    try:
                        data = json.loads(message)

                        # Process the received message
                        if data.get("type") == "command":
                            response = await process_command(data)
                            if response:
                                await command_queue.put(response)

                        elif data.get("type") == "ping":
                            # Handle ping messages
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
                        # Add sleep to avoid busy loop on error
                        await asyncio.sleep(0.1)

                    # Small delay to reduce CPU usage at end of each loop iteration
                    await asyncio.sleep(MIN_SLEEP_DELAY)

            except ConnectionClosed as e:
                logger.error(f"WebSocket connection closed: {e}")

            # Connection lost, cancel background tasks
            frame_task.cancel()
            position_task.cancel()
            health_task.cancel()
            try:
                await asyncio.gather(frame_task,
                                     position_task,
                                     health_task,
                                     return_exceptions=True)
            except asyncio.CancelledError:
                pass

            logger.info("WebSocket connection lost, will reconnect")
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")

            # Track failures and use exponential backoff
            total_connection_failures += 1
            reconnect_delay = min(max_reconnect_delay, reconnect_delay * 1.5)

            # Add jitter to avoid thundering herd problem
            jitter = random.uniform(0, 0.3 * reconnect_delay)
            actual_delay = reconnect_delay + jitter

            logger.info(
                f"Retrying connection in {actual_delay:.1f} seconds (attempt {total_connection_failures})..."
            )
            await asyncio.sleep(actual_delay)

            # If too many failures, restart hardware
            if total_connection_failures >= max_failures_before_reset:
                logger.warning(
                    f"Too many connection failures ({total_connection_failures}), restarting hardware..."
                )

                # Reset hardware
                stop_camera(picam2)
                stop_controller(controller)

                # Add delay before reinitializing
                await asyncio.sleep(5)

                # Reinitialize hardware
                initialize_camera()
                initialize_xeryon_controller()

                # Reset counter
                total_connection_failures = 0


async def main():
    """Entry point with proper shutdown handling."""
    global shutdown_requested

    try:
        await rpi_client()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        # Signal shutdown
        shutdown_requested = True
        logger.info("Shutting down...")

        # Cleanup hardware
        stop_camera(picam2)
        stop_controller(controller)

        # Cleanup and release resources
        gc.collect()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
