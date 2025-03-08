import asyncio
import websockets
import json
import base64
import sys
import time
from pathlib import Path

# Get the RPi ID from command line arguments or use a default
if len(sys.argv) > 1:
    STATION_ID = sys.argv[1]
else:
    STATION_ID = "RPI1"  # Default ID if none provided

# Load a test image and convert to base64
TEST_IMAGE_PATH = Path(__file__).parent.parent / "public" / "uploads" / "test-frame.jpg"

async def rpi_client():
    uri = f"ws://localhost:5000/rpi/{STATION_ID}"
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting test client for {STATION_ID}")

    # Read test image once
    try:
        with open(TEST_IMAGE_PATH, "rb") as f:
            test_frame = base64.b64encode(f.read()).decode('utf-8')
            print(f"Loaded test frame, size: {len(test_frame)} bytes")
    except FileNotFoundError:
        print("Test image not found, using small base64 test pattern")
        # Small red dot JPEG as base64
        test_frame = "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAKAAoDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD2SiiigD//2Q=="

    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"Connected to {uri}")

                # Send initial registration
                await ws.send(json.dumps({
                    "type": "register",
                    "status": "ready",
                    "message": f"Test client {STATION_ID} ready",
                    "rpi_id": STATION_ID
                }))

                # Send test frames periodically
                while True:
                    try:
                        frame_data = {
                            "type": "camera_frame",
                            "rpi_id": STATION_ID,
                            "frame": test_frame
                        }
                        await ws.send(json.dumps(frame_data))
                        print(f"Sent test frame, size: {len(test_frame)} bytes")
                        await asyncio.sleep(0.5)  # 2 FPS
                    except Exception as e:
                        print(f"Error sending frame: {e}")
                        break

        except Exception as e:
            print(f"Connection error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(rpi_client())
    except KeyboardInterrupt:
        print("Test client stopped")