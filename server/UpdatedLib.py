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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 50
TARGET_FPS = 30  # Increased from 20 to 30 for smoother feed
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1  # Reduced from 0.5 to 0.1 for more responsive position updates
FRAME_QUEUE_LIMIT = 1  # Reduced from 3 to 1 to always prioritize latest frame
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
CPU_MONITOR_INTERVAL = 10
MIN_SLEEP_DELAY = 0.0001  # Reduced to absolute minimum (0.1ms)
HEALTH_CHECK_INTERVAL = 10
RECONNECT_TIMEOUT = 30  # Reconnect if silent >30s
CAMERA_FLUSH_INTERVAL = 1  # Flush camera buffer every 1 second
USB_FLUSH_INTERVAL = 15  # Flush USB buffer every 15 seconds

# Globals
picam2 = None
controller = None
axis = None
demo_running = False
shutdown_requested = False
command_queue = asyncio.Queue()
frame_queue = deque(maxlen=FRAME_QUEUE_LIMIT)
reconnect_delay = 1
max_reconnect_delay = 30
total_connection_failures = 0
max_failures_before_reset = 5
last_successful_command_time = time.time()
last_successful_frame_time = time.time()
last_ping_response_time = time.time()
startup_time = time.time()
should_reconnect = False  # Signal reconnect

# Camera Functions
def initialize_camera():
    """Initialize camera with retry logic."""
    global picam2
    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
        logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
        
        # Flush initial buffer to get fresher frames
        for _ in range(5):
            _ = picam2.capture_array("main")
            
        time.sleep(0.5)  # Reduced from 1s to 0.5s
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
def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration parameters."""
    global axis
    if not axis:
        logger.error("Cannot set acce/dece: Axis not initialized")
        return False
    try:
        if acce_value is not None:
            acce_value = max(0, min(65500, int(acce_value)))
            axis.sendCommand(f"ACCE={acce_value}")
            logger.info(f"Set acceleration to {acce_value}")
        if dece_value is not None:
            dece_value = max(0, min(65500, int(dece_value)))
            axis.sendCommand(f"DECE={dece_value}")
            logger.info(f"Set deceleration to {dece_value}")
        return True
    except Exception as e:
        logger.error(f"Error setting acce/dece: {str(e)}")
        return False

def initialize_xeryon_controller():
    """Initialize Xeryon with robust serial retry."""
    global controller, axis
    try:
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found—attempting USB reset")
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
    """Run Xeryon demo."""
    global demo_running, axis, last_successful_command_time
    demo_running = True
    logger.info("Demo started")
    for _ in range(100):
        if not demo_running or not axis:
            break
        try:
            speed = random.uniform(10, 500)
            await asyncio.to_thread(axis.setSpeed, speed)
            logger.info(f"Demo: Speed {speed} mm/s")
            action = random.choice(["step", "scan"])
            if action == "step":
                direction = random.choice([1, -1])
                await asyncio.to_thread(axis.step, direction)
                logger.info(f"Demo: Step {direction} mm")
                last_successful_command_time = time.time()
                await asyncio.sleep(0.5)
            else:
                direction = random.choice([1, -1])
                await asyncio.to_thread(axis.startScan, direction)
                logger.info(f"Demo: Scan {'right' if direction == 1 else 'left'}")
                last_successful_command_time = time.time()
                await asyncio.sleep(random.uniform(0.5, 2))
                await asyncio.to_thread(axis.stopScan)
                logger.info("Demo: Scan stopped")
                last_successful_command_time = time.time()
            await asyncio.sleep(MIN_SLEEP_DELAY)
        except Exception as e:
            logger.error(f"Demo error: {str(e)}")
            demo_running = False
            break
    if demo_running:
        logger.info("Demo completed")
        try:
            await asyncio.to_thread(axis.setDPOS, 0)
            logger.info("Demo: DPOS 0 mm")
            last_successful_command_time = time.time()
        except Exception as e:
            logger.error(f"DPOS reset error: {str(e)}")
    demo_running = False

async def process_command(data):
    """Handle Xeryon commands and pings."""
    global demo_running, axis, last_successful_command_time, last_ping_response_time
    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration") or data.get("acce")
    dece_value = data.get("deceleration") or data.get("dece")
    response = {"status": "success", "rpiId": STATION_ID}

    try:
        if message_type == "ping":
            response.update({
                "type": "pong",
                "timestamp": timestamp,
                "rpiId": STATION_ID
            })
            last_ping_response_time = time.time()
            return response
        elif message_type == "pong":
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

        if not axis:
            raise Exception("Axis not initialized—cannot process command")

        response["message"] = f"Executing command '{command}'"
        logger.info(f"Processing command: {command}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}, acce: {acce_value}, dece: {dece_value}")

        last_successful_command_time = time.time()
        if command in ["acceleration", "acce"]:
            acce_value = acce_value or (int(direction) if direction.isdigit() else DEFAULT_ACCELERATION)
            set_acce_dece_params(acce_value=acce_value)
            response["message"] = f"Acceleration set to {acce_value}"
            return response
        elif command in ["deceleration", "dece"]:
            dece_value = dece_value or (int(direction) if direction.isdigit() else DEFAULT_DECELERATION)
            set_acce_dece_params(dece_value=dece_value)
            response["message"] = f"Deceleration set to {dece_value}"
            return response

        if acce_value or dece_value:
            set_acce_dece_params(acce_value, dece_value)
            if acce_value:
                response["acceleration"] = acce_value
            if dece_value:
                response["deceleration"] = dece_value

        # Sync DPOS to EPOS for move, stop, scan
        if command in ["move", "step", "stop", "scan"]:
            try:
                epos = await asyncio.to_thread(axis.getEPOS)
                await asyncio.to_thread(axis.setDPOS, epos)
                logger.debug(f"Synced DPOS to EPOS: {epos:.6f} mm")
            except Exception as e:
                logger.warning(f"DPOS sync failed: {str(e)}")

        if command in ["move", "step"]:
            if direction not in ["right", "left"]:
                raise ValueError(f"Invalid direction: {direction}")
            if step_size is None or not isinstance(step_size, (int, float)) or step_size < 0:
                raise ValueError(f"Invalid stepSize: {step_size}")
            if step_unit not in ["mm", "µm", "nm"]:
                raise ValueError(f"Invalid stepUnit: {step_unit}")
            step_value = float(step_size)
            if step_unit == "µm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
            final_step = step_value if direction == "right" else -step_value
            await asyncio.to_thread(axis.step, final_step)
            response["message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
            response["step_executed_mm"] = final_step
            logger.info(f"Move executed: {final_step:.6f} mm")
        elif command == "home":
            await asyncio.to_thread(axis.findIndex)
            epos = await asyncio.to_thread(axis.getEPOS)
            response["message"] = f"Homed to index, EPOS {epos:.6f} mm"
            response["epos_mm"] = epos
            logger.info(f"Homed, EPOS: {epos:.6f} mm")
        elif command == "speed":
            try:
                speed_value = float(direction)
            except ValueError:
                raise ValueError(f"Invalid speed direction: {direction}")
            await asyncio.to_thread(axis.setSpeed, speed_value)
            response["message"] = f"Speed set to {speed_value:.2f} mm/s"
            logger.info(f"Speed set: {speed_value:.2f} mm/s")
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
        elif command == "demo_start":
            if not demo_running:
                asyncio.create_task(run_demo())
                response["message"] = "Demo started"
                logger.info("Demo started")
            else:
                response["message"] = "Demo already running"
                logger.info("Demo already running")
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
        elif command == "stop":
            await asyncio.to_thread(axis.stopScan)
            await asyncio.to_thread(axis.setDPOS, 0)
            response["message"] = "Stopped, DPOS 0 mm"
            logger.info("Stopped, DPOS 0 mm")
        elif command == "reset_params":
            await asyncio.to_thread(axis.setSpeed, 500)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            response["message"] = "Parameters reset to defaults"
            logger.info("Parameters reset to defaults")
        else:
            raise ValueError(f"Unknown command: {command}")
    except Exception as e:
        response["status"] = "error"
        response["message"] = f"Command '{command}' failed: {str(e)}"
        logger.error(f"Command error: {str(e)}")
    return response

async def send_camera_frames(websocket):
    """Ultra-optimized camera frame sending with priority on real-time freshness."""
    global picam2, last_successful_frame_time
    frame_count = 0
    last_frame_time = time.time()
    frame_backlog = 0
    current_quality = JPEG_QUALITY
    
    # Single capture parameter for speed
    encode_params = [
        cv2.IMWRITE_JPEG_QUALITY, current_quality,
        cv2.IMWRITE_JPEG_OPTIMIZE, 1,
    ]

    while not shutdown_requested:
        try:
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.error("Camera not started, pausing frame sending")
                await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s
                continue

            # CRITICAL: Always prioritize freshness - capture new frame ASAP
            current_time = time.time()
            elapsed = current_time - last_frame_time
            
            # Immediate frame capture - don't wait for FPS target if backlogged
            if frame_backlog > 0 or elapsed >= 1.0 / TARGET_FPS:
                # Skip frame rate limiting entirely when backlogged
                pass
            else:
                # Very minimal sleep to respect FPS but keep responsive
                target_sleep = (1.0 / TARGET_FPS) - elapsed
                if target_sleep > 0.002:  # Only sleep if more than 2ms needed
                    await asyncio.sleep(min(target_sleep, 0.005))  # Cap at 5ms max
            
            # No sleep before frame capture - always get freshest frame
            frame = None
            try:
                # Capture freshest frame
                frame = picam2.capture_array("main")
                last_frame_time = time.time()  # Update time right after capture
            except Exception as e:
                logger.error(f"Frame capture failed: {str(e)}")
                await asyncio.sleep(0.01)  # Very minimal recovery delay
                continue
                
            if frame is None:
                logger.warning("Null frame captured")
                continue
                
            # Skip frame processing if we're extremely backlogged
            if frame_backlog > 10:
                frame_backlog += 1
                if frame_backlog % 20 == 0:
                    logger.warning(f"Extreme backlog: {frame_backlog} frames - skipping processing")
                continue
                
            # Track backlog
            current_time = time.time()
            elapsed = current_time - last_frame_time
            fps_target_delay = 1.0 / TARGET_FPS
            
            # Dynamic quality based on backlog
            if elapsed > fps_target_delay * 3:
                # Severe backlog
                frame_backlog += 1
                if frame_backlog % 5 == 0:
                    logger.debug(f"Camera backlog: {frame_backlog} frames")
                # Reduce quality more aggressively when severely behind
                current_quality = max(JPEG_QUALITY - 20, 20)
                encode_params[1] = current_quality
            elif elapsed > fps_target_delay * 1.5:
                # Moderate backlog
                frame_backlog += 1
                current_quality = max(JPEG_QUALITY - 10, 30)
                encode_params[1] = current_quality
            else:
                # Caught up or ahead
                frame_backlog = max(0, frame_backlog - 1)
                if current_quality < JPEG_QUALITY:
                    current_quality = min(current_quality + 5, JPEG_QUALITY)
                    encode_params[1] = current_quality

            # Skip timestamp overlay if severely backlogged (saves 1-2ms)
            if frame_backlog < 5:
                frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                try:
                    cv2.putText(frame, f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                except Exception:
                    pass  # Skip text on error - prioritize image delivery
            
            # Optimize frame encoding - use simpler parameters when backlogged
            try:
                _, buffer = cv2.imencode('.jpg', frame, encode_params)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Frame encoding failed: {str(e)}")
                continue
                
            # Clear frame queue if backlogged - always use latest frame
            if len(frame_queue) > 0 and frame_backlog > 2:
                frame_queue.clear()
                logger.debug("Cleared frame queue to prioritize latest frame")
            
            # Prepare frame data
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": jpg_as_text,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Replace any existing frame in queue with latest
            frame_queue.append(frame_data)
            
            # Send immediately - don't wait
            try:
                while frame_queue:
                    await websocket.send(json.dumps(frame_queue[0]))
                    frame_queue.popleft()
                frame_count += 1
                last_successful_frame_time = time.time()
                
                # Only log every 200 frames to reduce overhead
                if frame_count % 200 == 0:
                    logger.info(f"Sent frame {frame_count}, quality: {current_quality}")
            except Exception as e:
                logger.error(f"Frame send error: {str(e)}")
                await asyncio.sleep(0.01)  # Very minimal delay on error
            
        except Exception as e:
            logger.error(f"Camera frame error: {str(e)}")
            await asyncio.sleep(0.05)  # Minimal delay on error

async def send_position_updates(websocket):
    """Ultra-real-time position updates."""
    global axis, last_successful_command_time
    last_epos = None
    last_update_time = time.time()

    while not shutdown_requested:
        try:
            if not axis:
                logger.warning("Axis not initialized, pausing position updates")
                await asyncio.sleep(0.5)  # Reduced delay
                continue

            # Get current position with minimal delay
            try:
                epos = await asyncio.to_thread(axis.getEPOS)
            except Exception as e:
                logger.error(f"EPOS read error: {str(e)}")
                await asyncio.sleep(0.1)  # Very short error recovery
                continue
                
            # Always send if position changed OR at regular intervals
            current_time = time.time()
            elapsed = current_time - last_update_time
            
            if last_epos != epos or elapsed >= EPOS_UPDATE_INTERVAL:
                position_data = {
                    "type": "position_update",
                    "rpiId": STATION_ID,
                    "epos": epos,
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    await websocket.send(json.dumps(position_data))
                    last_epos = epos
                    last_update_time = current_time
                    last_successful_command_time = current_time
                    
                    # Only log occasionally to reduce overhead
                    if random.random() < 0.05:  # ~5% of updates
                        logger.debug(f"Position update: {epos:.6f} mm")
                except Exception as e:
                    logger.error(f"Position send error: {str(e)}")
                    await asyncio.sleep(0.05)  # Minimal error delay
            
            # Always use minimal sleep to give CPU time to other tasks
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
        except Exception as e:
            logger.error(f"Position update error: {str(e)}")
            await asyncio.sleep(0.1)  # Short recovery delay

async def health_checker(websocket):
    """Aggressive health checker with fast reconnect on issues."""
    global should_reconnect
    check_interval = HEALTH_CHECK_INTERVAL
    silent_warning_threshold = 10  # Log warning after 10s silence
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            ping_silence = current_time - last_ping_response_time
            
            # Adjust check interval based on silence
            if command_silence > 30 or ping_silence > 30:
                # Critical situation - check more frequently
                check_interval = 2
                should_reconnect = True
                logger.warning(f"Critical silence: cmd={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s")
                break  # Break immediately to trigger reconnect
            elif command_silence > 15 or ping_silence > 15:
                # Concerning - check more frequently
                check_interval = 5
                logger.warning(f"Extended silence: cmd={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s")
            elif command_silence > silent_warning_threshold or ping_silence > silent_warning_threshold:
                # Worth monitoring
                logger.debug(f"Silence noted: cmd={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s")
                check_interval = 8
            else:
                # Healthy
                check_interval = HEALTH_CHECK_INTERVAL
            
            # Send heartbeat
            ping_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID,
                "uptime": time.time() - startup_time
            }
            
            await websocket.send(json.dumps(ping_data))
            await asyncio.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"Health checker error: {str(e)}")
            should_reconnect = True
            break

async def flush_camera_buffer():
    """Aggressive camera buffer flushing."""
    global picam2
    while not shutdown_requested:
        try:
            if picam2 and hasattr(picam2, 'started') and picam2.started:
                # Capture multiple frames to ensure buffer is flushed
                for _ in range(3):
                    _ = picam2.capture_array("main")
                logger.debug("Camera buffer flushed")
            await asyncio.sleep(CAMERA_FLUSH_INTERVAL)
        except Exception as e:
            logger.error(f"Camera buffer flush error: {str(e)}")
            await asyncio.sleep(1)  # Shorter recovery
        
        # No additional sleep - run as frequently as configured

async def flush_usb_buffer():
    """Regular USB buffer flushing."""
    while not shutdown_requested:
        try:
            if os.path.exists(COM_PORT):
                with serial.Serial(COM_PORT, 115200, timeout=1) as ser:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                logger.debug(f"USB port {COM_PORT} buffers flushed")
            await asyncio.sleep(USB_FLUSH_INTERVAL)
        except Exception as e:
            logger.error(f"USB buffer flush error: {str(e)}")
            await asyncio.sleep(5)

async def command_processor():
    """Ultra-responsive command processor."""
    while not shutdown_requested:
        try:
            command = await command_queue.get()
            current_websocket = getattr(command_processor, 'websocket', None)
            if current_websocket:
                await current_websocket.send(json.dumps(command))
                logger.debug(f"Sent queued command: {command.get('type')} {command.get('command', '')}")
                
            # No sleep after sending - process next command immediately
        except Exception as e:
            logger.error(f"Command processor error: {str(e)}")
            await asyncio.sleep(0.1)  # Minimal error recovery
        
        # Minimal yield to prevent CPU hogging
        await asyncio.sleep(MIN_SLEEP_DELAY)

async def rpi_client():
    """Main client with single WebSocket."""
    global shutdown_requested, reconnect_delay, total_connection_failures, startup_time, should_reconnect
    startup_time = time.time()

    # Start buffer management tasks
    camera_flush_task = asyncio.create_task(flush_camera_buffer())
    usb_flush_task = asyncio.create_task(flush_usb_buffer())
    cmd_processor_task = asyncio.create_task(command_processor())

    logger.info(f"Starting RPi Client for {STATION_ID}")
    if not initialize_camera():
        logger.warning("First camera init failed, retrying...")
        await asyncio.sleep(1)
        initialize_camera()
    if not initialize_xeryon_controller():
        logger.warning("First Xeryon init failed, retrying...")
        await asyncio.sleep(1)
        initialize_xeryon_controller()

    connection_id = f"single_{int(time.time())}"
    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            # Use shorter timeout for faster failure detection
            async with websockets.connect(
                SERVER_URL, ping_interval=None, close_timeout=3
            ) as websocket:
                # Register immediately
                registration_msg = {
                    "type": "register",
                    "rpiId": STATION_ID,
                    "connectionType": "combined",
                    "status": "ready",
                    "message": f"RPi {STATION_ID} combined connection initialized",
                    "connectionId": connection_id,
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(registration_msg))
                logger.info("WebSocket connection established")
                command_processor.websocket = websocket

                # Start real-time tasks with higher priority
                frame_task = asyncio.create_task(send_camera_frames(websocket))
                position_task = asyncio.create_task(send_position_updates(websocket))
                health_task = asyncio.create_task(health_checker(websocket))

                total_connection_failures = 0
                reconnect_delay = 1
                should_reconnect = False

                try:
                    while not shutdown_requested and not should_reconnect:
                        try:
                            # Short timeout for faster detection of issues
                            message = await asyncio.wait_for(websocket.recv(), timeout=2)
                            
                            try:
                                data = json.loads(message)
                                if data.get("type") == "command":
                                    # Process commands immediately without queueing
                                    response = await process_command(data)
                                    if response:
                                        await websocket.send(json.dumps(response))
                                elif data.get("type") == "ping":
                                    # Respond to pings immediately
                                    await websocket.send(json.dumps({
                                        "type": "pong",
                                        "timestamp": data.get("timestamp"),
                                        "rpiId": STATION_ID
                                    }))
                                    last_ping_response_time = time.time()
                            except json.JSONDecodeError:
                                logger.error(f"Invalid JSON received")
                            except Exception as e:
                                logger.error(f"Message processing error: {str(e)}")
                        except asyncio.TimeoutError:
                            # Check silence thresholds
                            current_time = time.time()
                            cmd_silence = current_time - last_successful_command_time
                            ping_silence = current_time - last_ping_response_time
                            
                            if cmd_silence > RECONNECT_TIMEOUT or ping_silence > RECONNECT_TIMEOUT:
                                logger.warning(f"Silence timeout: cmd={cmd_silence:.1f}s, ping={ping_silence:.1f}s")
                                should_reconnect = True
                                break
                except ConnectionClosed as e:
                    logger.error(f"WebSocket closed: {str(e)}")
                
                # Connection ended - cancel tasks
                frame_task.cancel()
                position_task.cancel()
                health_task.cancel()
                try:
                    await asyncio.gather(frame_task, position_task, health_task, return_exceptions=True)
                except asyncio.CancelledError:
                    pass
                
                # Clear queue before reconnecting
                while not command_queue.empty():
                    try:
                        _ = command_queue.get_nowait()
                    except:
                        break
                
                await asyncio.sleep(1)  # Brief pause before reconnecting

        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            total_connection_failures += 1
            reconnect_delay = min(max_reconnect_delay, reconnect_delay * 1.5)
            jitter = random.uniform(0, 0.3 * reconnect_delay)
            await asyncio.sleep(reconnect_delay + jitter)

            if total_connection_failures >= max_failures_before_reset:
                logger.warning(f"Too many failures ({total_connection_failures}), restarting hardware")
                stop_camera(picam2)
                stop_controller(controller)
                await asyncio.sleep(3)  # Reduced from 5s to 3s
                initialize_camera()
                initialize_xeryon_controller()
                total_connection_failures = 0

async def main():
    """Entry point with shutdown handling."""
    global shutdown_requested
    try:
        await rpi_client()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        shutdown_requested = True
        logger.info("Shutting down")
        stop_camera(picam2)
        stop_controller(controller)
        gc.collect()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")