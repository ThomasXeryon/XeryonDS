#!/usr/bin/env python3
"""
Ultra Simple Client - Just sends commands
- No safety limits
- Immediate command execution
- Zero waiting for position
- Minimum code, maximum reliability
"""

import asyncio
import websockets
import json
import base64
import cv2
import time
import sys
import os
import logging
from datetime import datetime
import threading

# Will be imported on the actual RPi
try:
    from picamera2 import Picamera2
    import serial
    sys.path.append('/home/pi/Desktop/RemoteDemoStation/BasicServer/Python')
    from Xeryon import Xeryon, Stage, Units
    RUNNING_ON_RPI = True
except ImportError:
    RUNNING_ON_RPI = False
    logging.warning("Running in simulation mode (not on RPi)")

# ===== CONFIGURATION =====
STATION_ID = "RPI1"
SERVER_URL = "wss://xeryonremotedemostation.replit.app/rpi/RPI1"
RESOLUTION_WIDTH = 1280
RESOLUTION_HEIGHT = 720
JPEG_QUALITY = 70
TARGET_FPS = 25
COM_PORT = "/dev/ttyACM0"
EPOS_UPDATE_INTERVAL = 0.1  # 100ms

# Default parameters
DEFAULT_ACCELERATION = 32750
DEFAULT_DECELERATION = 32750
DEFAULT_SPEED = 500

# Global state
shutdown_requested = False
controller = None
axis = None
picam2 = None
current_position = 0.0
websocket = None
connected = False

# Logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger("XeryonClient")

# ===== XERYON CONTROLLER FUNCTIONS =====
def initialize_xeryon_controller():
    """Initialize Xeryon controller."""
    global controller, axis

    if not RUNNING_ON_RPI:
        return True

    try:
        logger.info(f"Initializing Xeryon controller on {COM_PORT}")
        controller = Xeryon(COM_port=COM_PORT, baudrate=115200)
        axis = controller.addAxis(Stage.XLA_312_3N, "X")
        controller.start()
        axis.setUnits(Units.mm)
        axis.sendCommand("POLI=50")
        axis.setSpeed(DEFAULT_SPEED)
        axis.sendCommand(f"ACCE={DEFAULT_ACCELERATION}")
        axis.sendCommand(f"DECE={DEFAULT_DECELERATION}")
        axis.sendCommand("ENBL=1")
        return True
    except Exception as e:
        logger.error(f"Xeryon controller initialization failed: {str(e)}")
        return False

def stop_controller():
    """Stop controller."""
    global controller, axis
    if not RUNNING_ON_RPI:
        return
    try:
        if controller:
            controller.stop()
    except Exception as e:
        logger.error(f"Error stopping controller: {str(e)}")
    finally:
        controller = None
        axis = None

# ===== CAMERA FUNCTIONS =====
def initialize_camera():
    """Initialize camera."""
    global picam2
    if not RUNNING_ON_RPI:
        return True
    try:
        logger.info("Initializing camera")
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={"size": (RESOLUTION_WIDTH, RESOLUTION_HEIGHT), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
        return True
    except Exception as e:
        logger.error(f"Camera initialization failed: {str(e)}")
        return False

def stop_camera():
    """Stop camera."""
    global picam2
    if not RUNNING_ON_RPI:
        return
    try:
        if picam2:
            if hasattr(picam2, 'stop'):
                picam2.stop()
    except Exception as e:
        logger.error(f"Error stopping camera: {str(e)}")
    finally:
        picam2 = None

# ===== COMMAND PROCESSING =====
async def process_command(data):
    """Just pass commands directly to controller - no processing."""
    global axis, current_position, websocket

    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit")
    timestamp = data.get("timestamp")
    acce_value = data.get("acceleration", data.get("acce"))
    dece_value = data.get("deceleration", data.get("dece"))

    response = {"status": "success", "rpiId": STATION_ID}

    # Handle ping/pong
    if message_type == "ping":
        response.update({
            "type": "pong",
            "timestamp": timestamp,
            "rpiId": STATION_ID
        })
        await websocket.send(json.dumps(response))
        return
    elif message_type == "pong" or message_type == "heartbeat":
        return

    # If not on RPi, just return simulation message
    if not RUNNING_ON_RPI or not axis:
        response["message"] = f"Simulation: {command}"
        await websocket.send(json.dumps(response))
        return

    try:
        # Handle direct commands
        if command in ["acceleration", "acce"] and (acce_value is not None or direction.isdigit()):
            value = acce_value if acce_value is not None else int(direction)
            axis.sendCommand(f"ACCE={value}")
            response["message"] = f"Set ACCE={value}"

        elif command in ["deceleration", "dece"] and (dece_value is not None or direction.isdigit()):
            value = dece_value if dece_value is not None else int(direction)
            axis.sendCommand(f"DECE={value}")
            response["message"] = f"Set DECE={value}"

        elif command in ["move", "step"] and step_size is not None:
            # Convert to mm
            step_value = float(step_size)
            if step_unit == "μm":
                step_value /= 1000
            elif step_unit == "nm":
                step_value /= 1_000_000
                
            # Apply direction
            final_step = step_value if direction == "right" else -step_value
            
            # Just execute the step
            axis.step(final_step)
            response["message"] = f"Moved {direction} by {step_size} {step_unit}"

        elif command == "stop":
            axis.sendCommand("STOP=0")
            response["message"] = "Stopped"

        elif command == "home":
            axis.sendCommand("DPOS=0")
            response["message"] = "Homed"

        elif command == "scan" and step_size is not None:
            # Extract parameters
            scan_distance = float(step_size)
            scan_min = current_position - scan_distance/2
            scan_max = current_position + scan_distance/2
            scan_cycles = int(data.get("scanCycles", 1))
            
            # Send scan commands
            axis.sendCommand(f"SCNL={scan_min}")
            axis.sendCommand(f"SCNH={scan_max}")
            axis.sendCommand(f"SCNN={scan_cycles}")
            axis.sendCommand("SCAN=1")
            response["message"] = f"Scanning {scan_distance}mm"

        else:
            # Try to send as raw command
            axis.sendCommand(command)
            response["message"] = f"Sent: {command}"

        # Send response
        await websocket.send(json.dumps(response))

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        response["status"] = "error"
        response["message"] = str(e)
        await websocket.send(json.dumps(response))

# ===== BACKGROUND TASKS =====
async def send_frames():
    """Send camera frames."""
    global websocket, connected
    
    frame_count = 0
    sleep_time = 1.0 / TARGET_FPS
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(1)
            continue
            
        try:
            # Capture frame
            if RUNNING_ON_RPI and picam2:
                try:
                    frame = picam2.capture_array("main")
                    if frame is None:
                        await asyncio.sleep(sleep_time)
                        continue
                except Exception as e:
                    await asyncio.sleep(sleep_time)
                    continue
            else:
                # Simple test frame
                frame_count += 1
                frame = np.zeros((RESOLUTION_HEIGHT, RESOLUTION_WIDTH, 3), dtype=np.uint8)
                frame[:, :] = (50, 50, 50)
                cv2.putText(frame, f"Frame: {frame_count}", (20, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            # Encode to JPEG
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            frame_data = base64.b64encode(buffer).decode('utf-8')
            
            # Get position
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    current_position = epos
                except:
                    pass
                    
            # Send frame
            message = {
                "type": "camera_frame",
                "frame": f"data:image/jpeg;base64,{frame_data}",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            if epos is not None:
                message["epos"] = epos
                
            try:
                await websocket.send(json.dumps(message))
            except Exception as e:
                await asyncio.sleep(sleep_time)
                continue
                
            # Sleep to maintain FPS
            await asyncio.sleep(sleep_time)
                
        except Exception as e:
            await asyncio.sleep(sleep_time)

async def send_positions():
    """Send position updates."""
    global websocket, connected, current_position
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(1)
            continue
            
        try:
            # Get position
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    current_position = epos
                except:
                    await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                    continue
            else:
                epos = current_position
                
            # Send position
            message = {
                "type": "position_update",
                "epos": epos,
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                await websocket.send(json.dumps(message))
            except:
                await asyncio.sleep(EPOS_UPDATE_INTERVAL)
                continue
                
            # Sleep
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)
            
        except Exception:
            await asyncio.sleep(EPOS_UPDATE_INTERVAL)

async def send_pings():
    """Send pings periodically."""
    global websocket, connected
    
    while not shutdown_requested:
        if not connected:
            await asyncio.sleep(5)
            continue
            
        try:
            # Send ping
            message = {
                "type": "ping",
                "rpiId": STATION_ID,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                await websocket.send(json.dumps(message))
            except:
                await asyncio.sleep(5)
                continue
                
            # Sleep
            await asyncio.sleep(5)
            
        except Exception:
            await asyncio.sleep(5)

# ===== MAIN CLIENT FUNCTION =====
async def run_client():
    """Main client loop."""
    global websocket, connected
    
    # Initialize hardware
    if RUNNING_ON_RPI:
        initialize_xeryon_controller()
        initialize_camera()
    
    # Start background tasks
    asyncio.create_task(send_frames())
    asyncio.create_task(send_positions())
    asyncio.create_task(send_pings())
    
    # Main connection loop
    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL}")
            websocket = await websockets.connect(SERVER_URL, ping_interval=None)
            logger.info("Connected")
            connected = True
            
            # Register
            register_message = {
                "type": "register",
                "rpiId": STATION_ID,
                "connectionType": "combined"
            }
            await websocket.send(json.dumps(register_message))
            
            # Main message loop
            while not shutdown_requested:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    await process_command(data)
                except Exception as e:
                    logger.error(f"Error: {str(e)}")
                    try:
                        # Test connection
                        await websocket.send(json.dumps({"type": "ping"}))
                    except:
                        break
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            connected = False
            await asyncio.sleep(1)
            
        finally:
            connected = False
            try:
                await websocket.close()
            except:
                pass

if __name__ == "__main__":
    try:
        # Import numpy if needed
        if not RUNNING_ON_RPI:
            import numpy as np
            
        # Run client
        asyncio.run(run_client())
    except KeyboardInterrupt:
        shutdown_requested = True
        if RUNNING_ON_RPI:
            stop_controller()
            stop_camera()