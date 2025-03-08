import asyncio
import websockets
import json
import base64
import cv2
import time
import sys

# Get the station ID from command line arguments or use a default
if len(sys.argv) > 1:
    STATION_ID = sys.argv[1]
else:
    STATION_ID = "RPI1"  # Default ID if none provided

# Only use production URL
SERVER_URL = "wss://xeryonremotedemostation.replit.app"

async def connect_to_server():
    # The server expects connections to /rpi/{rpiId}
    uri = f"{SERVER_URL}/rpi/{STATION_ID}"
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connecting with URI: {uri}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Station ID: {STATION_ID}")

    # Debug output
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WEBSOCKET DEBUG INFO:")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - Server URL: {SERVER_URL}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - Station ID: {STATION_ID}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - Complete URI: {uri}")

    while True:  # Reconnect loop
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connecting to {uri}...")

            async with websockets.connect(
                uri,
                extra_headers={
                    'User-Agent': 'RaspberryPi-Client/1.0',
                    'X-Station-ID': STATION_ID
                },
                ping_interval=30,
                ping_timeout=10,
                max_size=100 * 1024 * 1024  # 100MB max message size
            ) as websocket:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connected to server")

                # Send registration message
                registration_data = {
                    "type": "register",
                    "status": "ready",
                    "message": f"RPi {STATION_ID} online with camera",
                    "rpi_id": STATION_ID
                }
                await websocket.send(json.dumps(registration_data))
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sent registration message")

                # Try different camera ports to find the correct one
                camera_found = False
                for port in range(10):  # Try ports 0-9
                    cap = cv2.VideoCapture(port)
                    if cap.isOpened():
                        ret, test_frame = cap.read()
                        if ret:
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully connected to camera on port {port}")
                            camera_found = True
                            break
                        cap.release()

                if not camera_found:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error: Could not open camera on any port.")
                    continue

                # Set resolution to reduce bandwidth
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

                # Main loop to send camera frames
                while True:
                    try:
                        ret, frame = cap.read()
                        if not ret:
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to capture frame")
                            await asyncio.sleep(1)
                            continue

                        # Compress frame to JPEG with quality 70
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

                        # Verify JPEG header
                        if buffer[0] != 0xFF or buffer[1] != 0xD8:
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Warning: Invalid JPEG header")
                            continue

                        # Convert to base64
                        jpg_as_text = base64.b64encode(buffer).decode('utf-8')

                        # Debug frame data
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Frame info:", {
                            "original_size": len(buffer),
                            "base64_size": len(jpg_as_text),
                            "jpeg_header": f"{buffer[0]:02X} {buffer[1]:02X} {buffer[2]:02X}"
                        })

                        # Send frame
                        frame_data = {
                            "type": "camera_frame",
                            "rpi_id": STATION_ID,
                            "frame": jpg_as_text
                        }
                        await websocket.send(json.dumps(frame_data))

                        # Process any incoming messages
                        try:
                            message = await asyncio.wait_for(websocket.recv(), 0.01)
                            data = json.loads(message)
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received message:", data)
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error receiving message: {e}")

                        # Rate limit to 10 FPS
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Frame processing error: {e}")
                        await asyncio.sleep(1)

        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection error: {e}")
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting camera feed from RPi {STATION_ID}")
    try:
        asyncio.run(connect_to_server())
    except KeyboardInterrupt:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Camera feed stopped by user")