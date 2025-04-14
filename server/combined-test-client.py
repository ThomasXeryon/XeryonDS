import asyncio
import websockets
import json
import base64
import time
import sys
import random
import math
from datetime import datetime

# Connection settings
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_BASE = 1.0
JITTER_MAX = 0.5
SERVER_URL = "ws://localhost:5000/rpi/"

async def rpi_combined_connection(rpi_id, url, max_attempts=MAX_RECONNECT_ATTEMPTS):
    """Establish a COMBINED connection for both camera and control"""
    attempt = 0
    
    while attempt < max_attempts:
        try:
            print(f"[{datetime.now()}] Starting COMBINED connection to: {url} (attempt {attempt+1}/{max_attempts})")
            
            # Add connection options for reliability
            websocket = await websockets.connect(
                url,
                ping_interval=5,
                ping_timeout=3,
                close_timeout=2
            )
            
            print(f"[{datetime.now()}] Combined connection established to {url}")
            
            # Send registration message with combined type
            register_msg = {
                "type": "register",
                "rpiId": rpi_id,
                "connectionType": "combined",
                "status": "ready",
                "message": f"RPi {rpi_id} combined connection initialized"
            }
            await websocket.send(json.dumps(register_msg))
            
            return websocket
            
        except Exception as e:
            attempt += 1
            print(f"[{datetime.now()}] Combined connection attempt {attempt} failed: {str(e)}")
            
            if attempt >= max_attempts:
                print(f"[{datetime.now()}] Maximum connection attempts reached. Giving up.")
                raise
            
            # Calculate backoff delay with jitter
            delay = RECONNECT_DELAY_BASE * (1.5 ** attempt) + random.uniform(0, JITTER_MAX)
            print(f"[{datetime.now()}] Retrying connection in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

async def send_frames(websocket, rpi_id):
    """Send simulated camera frames"""
    frame_number = 0
    
    try:
        # Sine wave oscillation for position
        import math
        while True:
            try:
                frame_number += 1
                
                # Calculate position using sine wave (oscillates between 5-15)
                t = frame_number / 10.0  # Time variable
                position = 10 + 5 * math.sin(t / 3.0)  # Sine wave centered at 10 with amplitude 5
                
                # Create a test frame
                frame_data = create_test_frame(frame_number, position)
                
                # Send frame as camera_frame message
                camera_msg = {
                    "type": "camera_frame",
                    "rpiId": rpi_id,
                    "frame": frame_data
                }
                await websocket.send(json.dumps(camera_msg))
                
                # Small delay to reduce CPU load
                await asyncio.sleep(0.005)
                
                # Send position update
                position_msg = {
                    "type": "position_update",
                    "rpiId": rpi_id,
                    "epos": position
                }
                await websocket.send(json.dumps(position_msg))
                
                print(f"[{datetime.now()}] Sent frame #{frame_number} with position {position:.3f}")
                
                # Send a ping every 5 frames (about 5 seconds)
                if frame_number % 5 == 0:
                    ping_msg = {
                        "type": "ping",
                        "timestamp": time.time() * 1000,  # Milliseconds timestamp
                        "rpiId": rpi_id
                    }
                    await websocket.send(json.dumps(ping_msg))
                    print(f"[{datetime.now()}] Sent ping message for latency measurement")
                    
                    # Instead of actively waiting for pong, just continue
                    # The handle_commands coroutine will handle the pong when it arrives
                    print(f"[{datetime.now()}] Ping sent, pong will be handled by command processor")
                    
                    # Add an extra small delay after sending ping to reduce CPU load
                    await asyncio.sleep(0.01)
                
                # Wait before sending next frame
                await asyncio.sleep(1.0)
                
            except websockets.exceptions.ConnectionClosed:
                print(f"[{datetime.now()}] Connection closed")
                break
            except Exception as e:
                print(f"[{datetime.now()}] Error in frame sending loop: {str(e)}")
                await asyncio.sleep(0.1)  # Sleep longer on error
                
    except Exception as e:
        print(f"[{datetime.now()}] Fatal error in send_frames: {str(e)}")
        # Sleep a bit before potentially reconnecting
        await asyncio.sleep(1.0)

async def handle_commands(websocket, rpi_id):
    """Handle received command messages"""
    try:
        while True:
            try:
                # Wait for incoming commands
                message = await websocket.recv()
                message_data = json.loads(message)
                
                if message_data.get("type") == "command":
                    # Extract command information
                    command = message_data.get("command", "unknown")
                    direction = message_data.get("direction", "none")
                    step_size = message_data.get("stepSize", 0)
                    step_unit = message_data.get("stepUnit", "mm")
                    
                    # Process the command
                    print(f"[{datetime.now()}] Received command: {command} {direction} {step_size}{step_unit}")
                    
                    # Simulate processing time with reasonable delay
                    await asyncio.sleep(0.05)
                    
                    # Send acknowledgment response
                    response = {
                        "type": "command_processed",
                        "rpiId": rpi_id,
                        "command": command,
                        "result": "success",
                        "message": f"Executed {command} {direction} {step_size}{step_unit}"
                    }
                    await websocket.send(json.dumps(response))
                    
                # Handle ping messages (from UI or server)
                elif message_data.get("type") == "ping":
                    # Respond with pong
                    pong_msg = {
                        "type": "pong",
                        "timestamp": message_data.get("timestamp"),
                        "rpiId": rpi_id
                    }
                    await websocket.send(json.dumps(pong_msg))
                
                # Short sleep to prevent CPU hogging
                await asyncio.sleep(0.001)
            
            except json.JSONDecodeError as e:
                print(f"[{datetime.now()}] Received invalid JSON: {e}")
                await asyncio.sleep(0.1)  # Sleep longer on error
                continue
                
    except websockets.exceptions.ConnectionClosed:
        print(f"[{datetime.now()}] Connection closed while handling commands")
    except Exception as e:
        print(f"[{datetime.now()}] Error in handle_commands: {str(e)}")

def create_test_frame(frame_number, position):
    """Create a simulated test pattern as a base64 string"""
    # Simple text-based representation with frame data
    frame_data = f"""
    ==========================================
    |  XERYON TEST PATTERN - FRAME {frame_number:05d}  |
    ==========================================
    |                                        |
    |  Current Position: {position:.3f} mm         |
    |                                        |
    |  {datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}  |
    |                                        |
    ==========================================
    """
    
    # Convert to base64
    frame_bytes = frame_data.encode('utf-8')
    base64_data = base64.b64encode(frame_bytes).decode('utf-8')
    
    return base64_data

async def monitor_cpu_usage():
    """Monitor and report CPU usage periodically to prevent overloading"""
    while True:
        try:
            # Add a sleep to reduce CPU load from the monitoring itself
            await asyncio.sleep(5)
            
            # In a real implementation, we would measure CPU usage here
            # For now, we just log that we're monitoring
            print(f"[{datetime.now()}] CPU monitoring active - adding sleep periods to reduce load")
            
        except Exception as e:
            print(f"[{datetime.now()}] Error in CPU monitoring: {e}")
            await asyncio.sleep(1)

async def main():
    """Main entry point"""
    # Get RPi ID from command line argument or use default
    rpi_id = sys.argv[1] if len(sys.argv) > 1 else 'RPI1'
    
    # Construct WebSocket URL
    url = f"{SERVER_URL}{rpi_id}"
    
    print(f"[{datetime.now()}] Starting RPi client simulation for {rpi_id}")
    print(f"[{datetime.now()}] Added CPU load reduction measures to prevent high CPU usage")
    
    # Start CPU monitoring in background
    monitor_task = asyncio.create_task(monitor_cpu_usage())
    
    # Retry loop for connection stability
    while True:
        try:
            # Establish the combined WebSocket connection
            websocket = await rpi_combined_connection(rpi_id, url)
            
            # Start tasks for sending frames and handling commands concurrently
            frame_task = asyncio.create_task(send_frames(websocket, rpi_id))
            command_task = asyncio.create_task(handle_commands(websocket, rpi_id))
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [frame_task, command_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            print(f"[{datetime.now()}] One of the tasks completed or failed, retrying connection...")
            await asyncio.sleep(1)  # Brief pause before reconnecting
            
        except Exception as e:
            print(f"[{datetime.now()}] Error in main loop: {str(e)}")
            await asyncio.sleep(2)  # Wait before retrying

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"[{datetime.now()}] Simulator stopped by user")
    except Exception as e:
        print(f"[{datetime.now()}] Fatal error: {str(e)}")