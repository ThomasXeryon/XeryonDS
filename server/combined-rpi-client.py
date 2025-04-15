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
    RESOLUTION_WIDTH = 1280
    RESOLUTION_HEIGHT = 720
    JPEG_QUALITY = 70
    TARGET_FPS = 30
    COM_PORT = "/dev/ttyACM0"
    EPOS_UPDATE_INTERVAL = 0.05

    # Acceleration and deceleration defaults
    DEFAULT_ACCELERATION = 32750
    DEFAULT_DECELERATION = 32750

    # CPU Usage Management - Optimized for max responsiveness
    CPU_MONITOR_INTERVAL = 10  # seconds
    MIN_SLEEP_DELAY = 0.00005# 0.5ms minimum delay between operations - half the original delay for maximum responsiveness

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
    max_failures_before_reset = 2
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
                    logger.info(
                        f"Demo: Scan {'right' if direction == 1 else 'left'}")
                    await asyncio.sleep(random.uniform(0.5, 2))
                    await asyncio.to_thread(axis.stopScan)
                    logger.info("Demo: Scan stopped")

                # Add small delay to reduce CPU usage
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
            except Exception as e:
                logger.error(f"DPOS reset error: {str(e)}")
        demo_running = False


    async def process_command(data):
        """Handle Xeryon commands and pings."""
        global demo_running, axis, last_successful_command_time


        axis.sendCommand("ENBL=1")
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
        """Send camera frames in a background task - optimized for real-time performance."""
        global picam2, last_successful_frame_time

        frame_count = 0
        last_frame_time = time.time()
        frame_backlog = 0  # Track if we're falling behind

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

                # Real-time optimization: Skip frames if we're falling behind
                # This ensures we always send the most current frame
                if elapsed > frame_interval * 2:  # We're more than 2 frames behind
                    frame_backlog += 1
                    if frame_backlog % 10 == 0:  # Log only occasionally
                        logger.debug(
                            f"Camera feed running behind, skipping frames to catch up (backlog: {frame_backlog})"
                        )
                    # Don't sleep, capture a fresh frame immediately
                else:
                    frame_backlog = 0  # Reset backlog counter when caught up

                    # Only rate limit if we're ahead of schedule
                    if elapsed < frame_interval:
                        # Use a very short sleep to yield but still prioritize frame sending
                        await asyncio.sleep(min(frame_interval - elapsed,
                                                0.005))  # Maximum 5ms sleep

                # Use minimal delay to reduce CPU usage while keeping real-time priority
                await asyncio.sleep(MIN_SLEEP_DELAY)

                # Capture frame
                last_frame_time = time.time()
                try:
                    rgb_buffer = picam2.capture_array("main")
                    frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
                except Exception as e:
                    logger.error(f"Frame capture error: {e}")
                    await asyncio.sleep(0.01)  # Very short sleep on capture error
                    continue

                # Get timestamp for this frame
                frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                # Add ID number and timestamp to frame
                id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
                cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)

                # Encode with emphasis on speed over quality if we're falling behind
                jpeg_quality = JPEG_QUALITY
                if frame_backlog > 5:
                    # Reduce quality slightly if falling behind
                    jpeg_quality = max(JPEG_QUALITY - 10, 30)

                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')

                # Create and send the frame data with minimal delay
                frame_data = {
                    "type": "camera_frame",
                    "rpiId": STATION_ID,
                    "frame": jpg_as_text,
                    "timestamp": frame_time,
                    "frameNumber": frame_count
                }

                try:
                    # Prioritize sending the frame - no additional sleep before sending
                    await websocket.send(json.dumps(frame_data))
                    # Increment frame count
                    frame_count += 1
                    last_successful_frame_time = time.time()

                    # Log frame info only occasionally
                    if frame_count % 20 == 0:  # Reduced logging frequency
                        logger.debug(f"Sent frame {frame_count} at {frame_time}")
                except Exception as e:
                    logger.error(f"Failed to send frame: {e}")
                    # Use very short sleep on send error to keep trying quickly
                    await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Camera frame sending error: {str(e)}")
                # Short sleep on error to recover quickly
                await asyncio.sleep(0.1)

            # Minimal delay at end of loop - prefer real-time responsiveness
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


    async def flush_camera_buffer():
        """Periodically flush camera buffer to ensure smooth operation."""
        global picam2
        while not shutdown_requested:
            try:
                if picam2 and hasattr(picam2, 'started') and picam2.started:
                    # Flush camera buffers by capturing a few frames
                    # without processing them - prevents buffer buildup
                    for _ in range(3):
                        _ = picam2.capture_array("main")
                    logger.debug("Camera buffers flushed")
                await asyncio.sleep(30)  # Run every 30 seconds
            except Exception as e:
                logger.error(f"Camera buffer flush error: {e}")
                await asyncio.sleep(5)


    async def flush_usb_buffer():
        """Periodically flush USB buffers to prevent data buildup."""
        while not shutdown_requested:
            try:
                if os.path.exists(COM_PORT):
                    try:
                        with serial.Serial(COM_PORT, 115200, timeout=1) as ser:
                            ser.reset_input_buffer()
                            ser.reset_output_buffer()
                        logger.debug(f"USB port {COM_PORT} buffers flushed")
                    except Exception as e:
                        logger.error(f"Error flushing USB port: {e}")
                await asyncio.sleep(60)  # Run every 60 seconds
            except Exception as e:
                logger.error(f"USB buffer flush error: {e}")
                await asyncio.sleep(5)


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

        # Start buffer flush tasks for maximum responsiveness
        camera_flush_task = asyncio.create_task(flush_camera_buffer())
        usb_flush_task = asyncio.create_task(flush_usb_buffer())

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
