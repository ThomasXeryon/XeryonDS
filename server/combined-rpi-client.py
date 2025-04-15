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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
STATION_ID = "RPI1"
SERVER_URL = f"wss://xeryonremotedemostation.replit.app/rpi/{STATION_ID}"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 50
TARGET_FPS = 15
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1

# Acceleration and deceleration defaults
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750

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
        config = picam2.create_video_configuration(main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"})
        picam2.configure(config)
        picam2.start()
        logger.info(f"Camera initialized: {RESOLUTION_WIDTH}x{RESOLUTION_HEIGHT}")
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
    """Run Xeryon demo."""
    global demo_running, axis
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
                await asyncio.sleep(0.5)
            else:
                direction = random.choice([1, -1])
                await asyncio.to_thread(axis.startScan, direction)
                logger.info(f"Demo: Scan {'right' if direction == 1 else 'left'}")
                await asyncio.sleep(random.uniform(0.5, 2))
                await asyncio.to_thread(axis.stopScan)
                logger.info("Demo: Scan stopped")
        except Exception as e:
            logger.error(f"Demo error: {str(e)}")
            demo_running = False
            break
    if demo_running:
        logger.info("Demo completed")
        try:
            await asyncio.to_thread(axis.setDPOS, 0)
            logger.info("Demo: DPOS 0 mm")
        except Exception as e:
            logger.error(f"DPOS reset error: {str(e)}")
    demo_running = False

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
    
    logger.debug(f"COMMAND RECEIVED: {command}, acce: {acce_value}, dece: {dece_value}")
    
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
            raise Exception("Axis not initialized—cannot process command")
        
        response["message"] = f"Executing command '{command}'"
        logger.info(f"Processing command: {command}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}, acce: {acce_value}, dece: {dece_value}")
        
        # Handle acceleration and deceleration commands directly
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
    
    return response

async def send_camera_frames(websocket):
    """Send camera frames in a background task."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_frame_time = time.time()
    
    while not shutdown_requested:
        try:
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.error("Camera not started, pausing frame sending")
                await asyncio.sleep(1)
                continue
                
            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time
            
            # Rate limit frame sending to target FPS
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
            
            last_frame_time = time.time()
            rgb_buffer = picam2.capture_array("main")
            frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            
            # Get timestamp for this frame
            frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # Add ID number and timestamp to frame
            id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
            cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Encode and compress the frame
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            # Create and send the frame data
            frame_data = {
                "type": "camera_frame", 
                "rpiId": STATION_ID,
                "frame": jpg_as_text,
                "frameCount": frame_count,
                "timestamp": frame_time,
                "frameFormat": "jpg.base64"
            }
            await websocket.send(json.dumps(frame_data))
            frame_count += 1
            last_successful_frame_time = time.time()
            
        except Exception as e:
            logger.error(f"Error in send_camera_frames: {str(e)}")
            await asyncio.sleep(0.5)

async def send_position_updates(websocket):
    """Send position updates in a background task."""
    global axis
    
    EPOS_interval = 0
    last_update_time = time.time()
    
    while not shutdown_requested:
        try:
            if not axis:
                logger.debug("Axis not initialized, pausing position updates")
                await asyncio.sleep(1)
                continue
                
            current_time = time.time()
            elapsed = current_time - last_update_time
            last_update_time = current_time
            
            # Get EPOS value and send it
            EPOS_interval += elapsed
            if EPOS_interval >= EPOS_UPDATE_INTERVAL:
                epos = await asyncio.to_thread(axis.getEPOS)
                epos_data = {
                    "type": "position_update",
                    "rpiId": STATION_ID,
                    "epos": round(epos, 3),
                    "timestamp": datetime.now().isoformat()
                }
                await websocket.send(json.dumps(epos_data))
                EPOS_interval = 0
                
        except Exception as e:
            logger.error(f"Error in send_position_updates: {str(e)}")
            await asyncio.sleep(0.5)

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
            logger.debug(f"Health: command={command_silence:.1f}s, frame={frame_silence:.1f}s, ping={ping_silence:.1f}s")
            
            # Send a health check ping
            ping_data = {
                "type": "health_check",
                "timestamp": datetime.now().isoformat(),
                "rpiId": STATION_ID,
                "uptime": time.time() - startup_time
            }
            await websocket.send(json.dumps(ping_data))
            
            await asyncio.sleep(health_check_interval)
            
        except Exception as e:
            logger.error(f"Health checker error: {str(e)}")
            break  # Exit to trigger reconnection

async def command_processor():
    """Process queued commands in background."""
    while not shutdown_requested:
        try:
            command = await command_queue.get()
            
            # Add to websocket outgoing queue
            current_websocket = getattr(command_processor, 'websocket', None)
            if current_websocket:
                try:
                    await current_websocket.send(json.dumps(command))
                    logger.debug(f"Sent queued command: {command.get('type')} {command.get('command', '')}")
                except Exception as e:
                    logger.error(f"Failed to send queued command: {str(e)}")
                    # Put command back in queue
                    await command_queue.put(command)
            else:
                # Put command back in queue if no active websocket
                await command_queue.put(command)
                
            command_queue.task_done()
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Command processor error: {str(e)}")
            await asyncio.sleep(1)

async def rpi_client():
    """Main function to run the RPI client with a single WebSocket connection."""
    global shutdown_requested, reconnect_delay, total_connection_failures
    global startup_time
    
    startup_time = time.time()
    
    # Start the command processor task
    cmd_processor_task = asyncio.create_task(command_processor())
    
    # Initialize hardware
    logger.info(f"Starting RPi Client for {STATION_ID}")
    logger.info(f"Connecting to server: {SERVER_URL}")
    
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
            # Create a unique URL for each connection attempt
            websocket_url = f"{SERVER_URL}?type=combined&id={connection_id}"
            logger.info(f"Connecting to WebSocket server: {websocket_url}")
            
            async with websockets.connect(websocket_url, ping_interval=None) as websocket:
                # Register this websocket with the command processor
                command_processor.websocket = websocket
                
                # Send registration message with combined type
                await websocket.send(json.dumps({
                    "type": "register",
                    "status": "ready",
                    "connectionType": "combined",  # Using the new combined type
                    "message": f"RPi {STATION_ID} connected with single WebSocket",
                    "rpiId": STATION_ID
                }))
                
                logger.info(f"WebSocket connected: {websocket_url}")
                
                # Reset connection failures counter on successful connection
                total_connection_failures = 0
                reconnect_delay = 1  # Reset backoff on successful connection
                
                # Update timestamps to prevent false triggers
                last_successful_command_time = time.time()
                last_successful_frame_time = time.time()
                last_ping_response_time = time.time()
                
                # Start camera and position update tasks
                camera_task = asyncio.create_task(send_camera_frames(websocket))
                position_task = asyncio.create_task(send_position_updates(websocket))
                health_task = asyncio.create_task(health_checker(websocket))
                
                # Main loop for receiving commands
                while not shutdown_requested:
                    try:
                        # Use a timeout to avoid blocking forever
                        message = await asyncio.wait_for(websocket.recv(), 1.0)
                        
                        try:
                            data = json.loads(message)
                            logger.info(f"Received message: {data.get('type')}, command: {data.get('command', 'none')}")
                            
                            # Process command and get response
                            response = await process_command(data)
                            
                            # Send response if available
                            if response:
                                await websocket.send(json.dumps(response))
                                logger.info(f"Sent response: {response.get('message', '')}")
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Received invalid JSON: {message[:100]}...")
                            
                    except asyncio.TimeoutError:
                        # No message received, just continue
                        pass
                        
                    except Exception as e:
                        logger.error(f"Error in main receive loop: {str(e)}")
                        logger.exception("Detailed traceback:")
                        break
                
                # Clean up tasks when the main loop exits
                for task in [camera_task, position_task, health_task]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                
                # On clean disconnect, create a new connection ID
                connection_id = f"single_{int(time.time())}"
                
        except Exception as e:
            total_connection_failures += 1
            logger.error(f"WebSocket connection error ({total_connection_failures}): {str(e)}")
            
            # Check if we need to reset hardware after too many failures
            if total_connection_failures >= max_failures_before_reset:
                logger.warning(f"Too many connection failures ({total_connection_failures}), resetting hardware")
                
                # Stop and restart hardware
                stop_camera(picam2)
                stop_controller(controller)
                await asyncio.sleep(2)
                initialize_camera()
                initialize_xeryon_controller()
                
                # Reset failure counter after hardware reset
                total_connection_failures = 0
            
            # Use exponential backoff for reconnection
            logger.info(f"Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
            
            # Create a new connection ID for the next attempt
            connection_id = f"single_{int(time.time())}"

async def main():
    """Entry point with proper shutdown handling."""
    global shutdown_requested
    
    try:
        # Run the client
        await rpi_client()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        shutdown_requested = True
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
    finally:
        # Clean shutdown of resources
        shutdown_requested = True
        logger.info("Shutting down...")
        if axis:
            try:
                # Issue stop command to ensure motor stops moving
                if axis:
                    axis.stopScan()
                    logger.info("Motor stopped")
            except:
                pass
        stop_controller(controller)
        stop_camera(picam2)
        logger.info("Shutdown complete")

if __name__ == "__main__":
    # Get RPi ID from command line if provided
    if len(sys.argv) > 1:
        STATION_ID = sys.argv[1]
        logger.info(f"Using command line RPi ID: {STATION_ID}")
    
    # Run the main function
    asyncio.run(main())