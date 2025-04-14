import asyncio
import websockets
import json
from datetime import datetime
import sys
import random
import time

# Connection retry settings
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_BASE = 1.0  # Base delay in seconds
JITTER_MAX = 0.5  # Maximum random jitter in seconds

# Function to create a new camera connection with retry logic
async def rpi_camera_connection(rpi_id, url, max_attempts=MAX_RECONNECT_ATTEMPTS):
    attempt = 0
    
    while attempt < max_attempts:
        try:
            print(f"[{datetime.now()}] Starting CAMERA connection to: {url} (attempt {attempt+1}/{max_attempts})")
            
            # Add connection options to make reconnection more reliable
            camera_ws = await websockets.connect(
                url,
                ping_interval=10,  # Send ping every 10 seconds
                ping_timeout=5,    # Expect pong within 5 seconds
                close_timeout=2    # Wait 2 seconds to close connection 
            )
            
            print(f"[{datetime.now()}] Camera connection established to {url}")
            
            # Send registration message with camera type
            register_msg = {
                "type": "register",
                "rpiId": rpi_id, 
                "connectionType": "camera",
                "status": "ready",
                "message": f"RPi {rpi_id} camera connection initialized"
            }
            await camera_ws.send(json.dumps(register_msg))
            print(f"[{datetime.now()}] Sent camera registration message")
            return camera_ws
            
        except Exception as e:
            attempt += 1
            print(f"[{datetime.now()}] Camera connection attempt {attempt} failed: {str(e)}")
            
            if attempt >= max_attempts:
                print(f"[{datetime.now()}] Maximum camera connection attempts reached. Giving up.")
                raise
            
            # Calculate backoff delay with jitter for more resilient reconnection
            delay = RECONNECT_DELAY_BASE * (1.5 ** attempt) + random.uniform(0, JITTER_MAX)
            print(f"[{datetime.now()}] Retrying camera connection in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

# Function to create a new control connection with retry logic
async def rpi_control_connection(rpi_id, url, max_attempts=MAX_RECONNECT_ATTEMPTS):
    attempt = 0
    
    while attempt < max_attempts:
        try:
            print(f"[{datetime.now()}] Starting CONTROL connection to: {url} (attempt {attempt+1}/{max_attempts})")
            
            # Add connection options to make reconnection more reliable
            control_ws = await websockets.connect(
                url,
                ping_interval=5,   # Send ping more frequently on control connection
                ping_timeout=3,    # Expect pong within 3 seconds
                close_timeout=2    # Wait 2 seconds to close connection 
            )
            
            print(f"[{datetime.now()}] Control connection established to {url}")
            
            # Send registration message with control type
            register_msg = {
                "type": "register",
                "rpiId": rpi_id,
                "connectionType": "control",
                "status": "ready",
                "message": f"RPi {rpi_id} control connection initialized"
            }
            await control_ws.send(json.dumps(register_msg))
            print(f"[{datetime.now()}] Sent control registration message")
            return control_ws
            
        except Exception as e:
            attempt += 1
            print(f"[{datetime.now()}] Control connection attempt {attempt} failed: {str(e)}")
            
            if attempt >= max_attempts:
                print(f"[{datetime.now()}] Maximum control connection attempts reached. Giving up.")
                raise
            
            # Calculate backoff delay with jitter for more resilient reconnection
            delay = RECONNECT_DELAY_BASE * (1.5 ** attempt) + random.uniform(0, JITTER_MAX)
            print(f"[{datetime.now()}] Retrying control connection in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

async def rpi_client(rpi_id='RPI1', server_url=None):
    if not server_url:
        # Try different URLs
        base_urls = [
            "ws://localhost:5000/rpi",         # Local dev
            "ws://0.0.0.0:5000/rpi",          # Direct IP
            "wss://xeryonremotedemostation.replit.app/rpi"  # Production
        ]
    else:
        base_urls = [server_url.rsplit('/', 1)[0]]  # Remove the last part (RPi ID) if present

    print(f"[{datetime.now()}] Starting RPi client simulation for {rpi_id}")

    for base_url in base_urls:
        url = f"{base_url}/{rpi_id}"
        
        try:
            # Start both camera and control connections in parallel
            connection_tasks = [
                rpi_camera_connection(rpi_id, url),
                rpi_control_connection(rpi_id, url)
            ]
            
            # Wait for both connections to be established
            camera_ws, control_ws = await asyncio.gather(*connection_tasks)
            
            print(f"[{datetime.now()}] Both camera and control connections established")

            # Simulate sending camera frames and processing commands
            frame_count = 0
            running = True
            
            # Function to check for and process control connection messages
            async def process_control_messages():
                nonlocal running
                while running:
                    try:
                        # Check for incoming control messages
                        message = await asyncio.wait_for(control_ws.recv(), 0.1)
                        data = json.loads(message)
                        
                        # Handle ping/pong messages
                        if data.get("type") == "pong":
                            print(f"[{datetime.now()}] Received pong response on control connection")
                        elif data.get("type") == "command":
                            # Process command
                            command = data.get('command', 'unknown')
                            direction = data.get('direction', 'none')
                            stepSize = data.get('stepSize', 0)
                            stepUnit = data.get('stepUnit', 'mm')
                            acce = data.get('acce', None)  # Acceleration parameter
                            dece = data.get('dece', None)  # Deceleration parameter
                            
                            # Handle both old and new command names
                            display_command = command
                            if command == 'acceleration' or command == 'acce':
                                display_command = 'acceleration'
                            elif command == 'deceleration' or command == 'dece':
                                display_command = 'deceleration'
                            
                            # Create cleaner command display string without duplication or parameter names
                            cmd_display = f"{direction} {stepSize}{stepUnit}"
                            if acce is not None:
                                cmd_display += f" {acce}"  # Acceleration value without parameter name
                            if dece is not None:
                                cmd_display += f" {dece}"  # Deceleration value without parameter name
                                
                            print(f"[{datetime.now()}] Received command: {display_command} ({cmd_display})")
                            
                            # Respond to commands with success message
                            response = {
                                "type": "rpi_response",
                                "status": "success",
                                "message": f"Command '{display_command}' executed successfully"
                            }
                            await control_ws.send(json.dumps(response))
                        else:
                            print(f"[{datetime.now()}] Received on control connection: {data}")
                    except asyncio.TimeoutError:
                        # No messages received, continue
                        pass
                    except websockets.exceptions.ConnectionClosed:
                        print(f"[{datetime.now()}] Control connection closed")
                        running = False
                        break
                    except Exception as e:
                        print(f"[{datetime.now()}] Error receiving control message: {str(e)}")
                        
                    # Small delay to prevent CPU hogging
                    await asyncio.sleep(0.01)
            
            # Start the control message processing task
            control_task = asyncio.create_task(process_control_messages())
            
            # Main loop for camera data
            try:
                import math
                while running:
                    try:
                        # Create a simulated frame (just a counter for testing)
                        frame_data = {
                            "type": "camera_frame",
                            "rpiId": rpi_id,
                            "frame": "SGVsbG8gV29ybGQ="  # Base64 "Hello World" as test data
                        }
                        await camera_ws.send(json.dumps(frame_data))
                        
                        # Also send position data update (EPOS value)
                        # Send a sine wave oscillation for interesting movement, using -30 to +30 range
                        # Currently using a portion of the range from -15 to +15
                        position_value = round(0.0 + 15.0 * math.sin(frame_count * 0.2), 3)
                        position_data = {
                            "type": "position_update",
                            "rpiId": rpi_id,
                            "epos": position_value
                        }
                        await camera_ws.send(json.dumps(position_data))
                        
                        frame_count += 1
                        print(f"[{datetime.now()}] Sent frame #{frame_count} with position {position_value}")

                        # Occasionally send a ping message to measure latency
                        if frame_count % 5 == 0:  # Every 5 frames, send a ping
                            ping_data = {
                                "type": "ping",
                                "timestamp": datetime.now().isoformat(),
                                "rpiId": rpi_id
                            }
                            await camera_ws.send(json.dumps(ping_data))
                            print(f"[{datetime.now()}] Sent ping message for latency measurement")

                        # Process any incoming camera connection messages
                        try:
                            message = await asyncio.wait_for(camera_ws.recv(), 0.1)
                            data = json.loads(message)
                            
                            # Handle ping/pong messages on camera connection
                            if data.get("type") == "pong":
                                print(f"[{datetime.now()}] Received pong response on camera connection")
                            else:
                                print(f"[{datetime.now()}] Received on camera connection: {data}")
                                
                        except asyncio.TimeoutError:
                            # No messages received, continue sending frames
                            pass
                        except Exception as e:
                            print(f"[{datetime.now()}] Error receiving camera message: {str(e)}")

                        # Wait before sending next frame
                        await asyncio.sleep(1)  # Send a frame every second

                    except websockets.exceptions.ConnectionClosed:
                        print(f"[{datetime.now()}] Camera connection closed")
                        running = False
                        break
                    except Exception as e:
                        print(f"[{datetime.now()}] Error in camera loop: {str(e)}")
                        running = False
                        break
                        
                # Wait for control task to complete when main loop ends
                control_task.cancel()
                try:
                    await control_task
                except asyncio.CancelledError:
                    pass
                    
            except Exception as e:
                print(f"[{datetime.now()}] Error in main processing: {str(e)}")
                if not control_task.done():
                    control_task.cancel()

        except Exception as e:
            print(f"[{datetime.now()}] Connection to {url} failed: {str(e)}")
            print(f"[{datetime.now()}] Error type: {type(e).__name__}")
            continue

        print(f"[{datetime.now()}] Connection closed, attempting reconnect...")
        await asyncio.sleep(5)  # Wait before reconnecting

if __name__ == "__main__":
    # Get RPi ID from command line argument or use default
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else 'RPI1'
    server_url = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        asyncio.run(rpi_client(rpi_id, server_url))
    except KeyboardInterrupt:
        print(f"[{datetime.now()}] Shutting down RPi client...")