import asyncio
import websockets
import json
from datetime import datetime
import sys

# Function to create a new camera connection
async def rpi_camera_connection(rpi_id, url):
    print(f"[{datetime.now()}] Starting CAMERA connection to: {url}")
    camera_ws = await websockets.connect(url)
    print(f"[{datetime.now()}] Camera connection established to {url}")
    
    # Send registration message with camera type
    register_msg = {
        "type": "register",
        "connectionType": "camera",
        "status": "ready",
        "message": f"RPi {rpi_id} camera connection initialized"
    }
    await camera_ws.send(json.dumps(register_msg))
    print(f"[{datetime.now()}] Sent camera registration message")
    return camera_ws

# Function to create a new control connection
async def rpi_control_connection(rpi_id, url):
    print(f"[{datetime.now()}] Starting CONTROL connection to: {url}")
    control_ws = await websockets.connect(url)
    print(f"[{datetime.now()}] Control connection established to {url}")
    
    # Send registration message with control type
    register_msg = {
        "type": "register",
        "connectionType": "control",
        "status": "ready",
        "message": f"RPi {rpi_id} control connection initialized"
    }
    await control_ws.send(json.dumps(register_msg))
    print(f"[{datetime.now()}] Sent control registration message")
    return control_ws

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
            camera_ws = await rpi_camera_connection(rpi_id, url)
            control_ws = await rpi_control_connection(rpi_id, url)
            
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
                            
                            print(f"[{datetime.now()}] Received command: {command} {direction} {stepSize}{stepUnit}")
                            
                            # Respond to commands with success message
                            response = {
                                "type": "rpi_response",
                                "status": "success",
                                "message": f"Command '{command}' executed successfully"
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
                        # Send a sine wave oscillation for interesting movement
                        position_value = round(10.0 + 5.0 * math.sin(frame_count * 0.2), 3)
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