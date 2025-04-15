"""
EXTREME CPU OPTIMIZATION FOR RASPBERRY PI CLIENT
Version 2.0 - High Performance Edition

Optimized for maximum responsiveness while maintaining high resolution and FPS.
This script provides targeted optimizations to reduce CPU usage on Raspberry Pi
without sacrificing performance or video quality.
"""

import asyncio
import json
import time
import logging
import base64
import os
import sys
import random
import subprocess
from datetime import datetime
from collections import deque
import threading
from functools import lru_cache

# =================================================================
# HIGH PERFORMANCE CONFIGURATION
# =================================================================

# Station identification
STATION_ID = "RPI1"

# Network settings - Do not change these values
WEBSOCKET_PING_INTERVAL = 5
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_BASE = 1.0
RECONNECT_JITTER_MAX = 0.5

# Camera settings - High resolution configuration
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_ROTATION = 180
CAMERA_FPS = 30
CAMERA_FRAME_INTERVAL = 1.0 / CAMERA_FPS  # 30 FPS
CAMERA_FRAME_QUALITY = 50  # JPEG quality (0-100)
CAMERA_FRAME_RESIZE = 1.0  # No resize to maintain full resolution

# Position update settings
EPOS_UPDATE_INTERVAL = 0.1  # 10 updates per second

# Health check settings
HEALTH_CHECK_INTERVAL = 5.0  # Check every 5 seconds
MAX_SILENCE_DURATION = 20.0  # Consider connection dead after 20s without activity

# CPU monitoring settings
CPU_MONITOR_INTERVAL = 10.0   # Check CPU every 10 seconds
CPU_HIGH_THRESHOLD = 90.0    # Above this is high usage (%)
CPU_CRITICAL_THRESHOLD = 95.0 # Above this is critical (%)

# Performance optimization settings
JSON_CACHE_SIZE = 100         # Number of JSON message templates to cache
MESSAGE_QUEUE_SIZE = 100      # Max messages to queue before dropping
LOG_BUFFER_SIZE = 100         # Number of log entries to buffer
LOG_FLUSH_INTERVAL = 10.0     # Seconds between log flushes

# Default actuator settings
DEFAULT_SPEED = 500           # Default speed (mm/s)
DEFAULT_ACCELERATION = 32750  # Default acceleration
DEFAULT_DECELERATION = 32750  # Default deceleration

# Memory management
GC_INTERVAL = 300.0           # Force garbage collection every 5 minutes
USB_FLUSH_INTERVAL = 60.0     # Flush USB port every 60 seconds
CAMERA_BUFFER_FLUSH_INTERVAL = 30.0  # Flush camera buffer every 30 seconds

# =================================================================
# OPTIMIZED LOGGING SETUP
# =================================================================

class BufferedHandler(logging.StreamHandler):
    """A logging handler that buffers records before flushing to reduce I/O."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buffer = []
        self.buffer_lock = threading.Lock()
        self.last_flush_time = time.time()
        
    def emit(self, record):
        with self.buffer_lock:
            self.buffer.append(record)
            
            # Flush if buffer is full or it's been a while
            current_time = time.time()
            if (len(self.buffer) >= LOG_BUFFER_SIZE or 
                current_time - self.last_flush_time >= LOG_FLUSH_INTERVAL):
                self.flush()
                
    def flush(self):
        with self.buffer_lock:
            if not self.buffer:
                return
                
            for record in self.buffer:
                try:
                    super().emit(record)
                except Exception:
                    pass
                    
            self.buffer.clear()
            self.last_flush_time = time.time()
            super().flush()

def setup_optimized_logging():
    """Set up logging optimized for lower CPU usage."""
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add buffered handler
    handler = BufferedHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Set level based on environment
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    return root_logger

# Initialize logger
logger = setup_optimized_logging()

# =================================================================
# PERFORMANCE OPTIMIZATION FUNCTIONS
# =================================================================

@lru_cache(maxsize=JSON_CACHE_SIZE)
def get_cached_json(message_type, **kwargs):
    """Get cached JSON string for frequently sent message types."""
    base_message = {"type": message_type, "rpiId": STATION_ID}
    base_message.update(kwargs)
    return json.dumps(base_message)

def set_cpu_governor(governor="performance"):
    """Set the CPU governor to control power/performance balance.
    
    For high-performance mode, we use 'performance' which keeps CPU at max frequency.
    """
    try:
        cmd = f"echo {governor} | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
        subprocess.run(cmd, shell=True)
        logger.info(f"CPU governor set to {governor}")
        return True
    except Exception as e:
        logger.error(f"Failed to set CPU governor: {e}")
        return False

def optimize_memory_usage():
    """Apply various memory optimizations."""
    try:
        import gc
        gc.collect()
        return True
    except Exception as e:
        logger.error(f"Failed to optimize memory: {e}")
        return False

# =================================================================
# CAMERA OPTIMIZATION FUNCTIONS
# =================================================================

def initialize_optimized_camera():
    """Initialize camera with optimized settings for high performance."""
    try:
        # Import picamera2 locally to avoid import errors
        from picamera2 import Picamera2
        
        picam2 = Picamera2()
        camera_config = picam2.create_video_configuration(
            main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"},
            controls={"FrameDurationLimits": (33333, 33333)}  # Force 30 FPS
        )
        picam2.configure(camera_config)
        picam2.start()
        
        # Wait for camera to initialize
        time.sleep(1.0)
        
        return picam2
    
    except ImportError:
        logger.info("Picamera2 not available, falling back to OpenCV")
        
        # Import cv2 locally to avoid import errors
        import cv2
        
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        
        # Check if camera opened successfully
        if not cap.isOpened():
            logger.error("Failed to open camera with OpenCV")
            return None
            
        # Discard first few frames to stabilize
        for _ in range(3):
            cap.read()
            
        return cap

def capture_optimized_frame(camera):
    """Capture a frame with optimized processing for maximum quality with minimal CPU."""
    try:
        # Import dependencies locally
        import cv2
        
        # Check if camera is picamera2 or OpenCV VideoCapture
        if hasattr(camera, 'capture_array'):
            # Picamera2
            frame = camera.capture_array("main")
        else:
            # OpenCV VideoCapture
            ret, frame = camera.read()
            if not ret:
                logger.error("Failed to capture frame with OpenCV")
                return None
        
        # Apply rotation if needed
        if CAMERA_ROTATION != 0:
            if CAMERA_ROTATION == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif CAMERA_ROTATION == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif CAMERA_ROTATION == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
        # Encode to JPEG with quality setting - No resize to maintain full resolution
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CAMERA_FRAME_QUALITY]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        
        # Convert to base64
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        
        return jpg_as_text
        
    except Exception as e:
        logger.error(f"Frame capture error: {e}")
        return None

# =================================================================
# USB AND CAMERA BUFFER MANAGEMENT
# =================================================================

def flush_usb_port(device_path=None):
    """Flush USB port buffers to prevent data buildup and latency issues."""
    try:
        # If no specific device is provided, try to find Xeryon controller or camera devices
        if not device_path:
            # Common paths for USB serial devices on Raspberry Pi
            potential_paths = [
                "/dev/ttyACM0",  # Default path for Xeryon controller
                "/dev/ttyUSB0",  # Common for USB-to-serial adapters
                "/dev/video0"    # For USB cameras
            ]
            
            for path in potential_paths:
                if os.path.exists(path):
                    device_path = path
                    break
        
        if not device_path or not os.path.exists(device_path):
            logger.debug("No USB device found to flush")
            return False
            
        # For serial devices
        if "tty" in device_path:
            import serial
            try:
                # Open, flush and close the serial port
                ser = serial.Serial(device_path, 115200, timeout=1)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                ser.flush()
                ser.close()
                logger.debug(f"Flushed serial device: {device_path}")
                return True
            except Exception as e:
                logger.error(f"Error flushing serial device {device_path}: {e}")
                return False
                
        # For camera devices
        elif "video" in device_path:
            try:
                # Execute system command to flush the device buffer
                cmd = f"echo 3 > /proc/sys/vm/drop_caches && cat /dev/null > {device_path}"
                subprocess.run(cmd, shell=True, check=True)
                logger.debug(f"Flushed camera device: {device_path}")
                return True
            except Exception as e:
                logger.error(f"Error flushing camera device {device_path}: {e}")
                return False
        
        return False
    except Exception as e:
        logger.error(f"USB flush error: {e}")
        return False

def flush_camera_buffers(camera):
    """Flush the camera buffers to prevent memory buildup."""
    try:
        if not camera:
            return False
            
        # For picamera2
        if hasattr(camera, 'capture_array'):
            # Picamera2 doesn't have a direct flush method, but we can 
            # capture and discard a few frames to clear internal buffers
            for _ in range(3):
                _ = camera.capture_array("main")
            logger.debug("Flushed Picamera2 buffers")
            return True
            
        # For OpenCV camera
        elif hasattr(camera, 'grab'):
            # For OpenCV, grabbing frames (without decoding) is faster
            for _ in range(5):
                camera.grab()  # Just grab frames without decoding
            logger.debug("Flushed OpenCV camera buffers")
            return True
            
        return False
    except Exception as e:
        logger.error(f"Camera buffer flush error: {e}")
        return False

# =================================================================
# OPTIMIZED WEBSOCKET COMMUNICATION
# =================================================================

class MessageQueue:
    """Optimized message queue with priority handling."""
    
    def __init__(self, max_size=MESSAGE_QUEUE_SIZE):
        self.high_priority = deque(maxlen=max_size // 2)
        self.normal_priority = deque(maxlen=max_size // 2)
        self.lock = threading.Lock()
        
    def add(self, message, high_priority=False):
        """Add a message to the queue with priority."""
        with self.lock:
            if high_priority:
                self.high_priority.append(message)
            else:
                self.normal_priority.append(message)
                
    def get(self):
        """Get the next message, prioritizing high-priority messages."""
        with self.lock:
            if self.high_priority:
                return self.high_priority.popleft()
            elif self.normal_priority:
                return self.normal_priority.popleft()
            else:
                return None
                
    def clear(self):
        """Clear all queued messages."""
        with self.lock:
            self.high_priority.clear()
            self.normal_priority.clear()
            
    def __len__(self):
        return len(self.high_priority) + len(self.normal_priority)

async def send_camera_frames(websocket, camera):
    """Send camera frames in a background task with optimized performance."""
    frame_count = 0
    next_frame_time = time.time()
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Only capture and send frames at the specified interval
        if current_time >= next_frame_time:
            # Calculate next frame time - strict timing for consistent FPS
            next_frame_time = current_time + CAMERA_FRAME_INTERVAL
            
            # Skip frame if we're too far behind to maintain timing
            delay = time.time() - current_time
            if delay > CAMERA_FRAME_INTERVAL * 2:
                logger.debug(f"Skipping frame due to processing delay: {delay:.3f}s")
                continue
                
            try:
                # Capture frame with optimized settings
                frame_data = capture_optimized_frame(camera)
                if not frame_data:
                    continue
                    
                # Prepare the message
                message = {
                    "type": "camera_frame",
                    "rpiId": STATION_ID,
                    "frame": frame_data,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Send frame
                await websocket.send(json.dumps(message))
                frame_count += 1
                
                # Debug logging less frequently to reduce CPU
                if frame_count % 30 == 0:  # Log once per second at 30 FPS
                    logger.debug(f"Sent frame #{frame_count}")
                    
            except Exception as e:
                logger.error(f"Error sending camera frame: {e}")
                await asyncio.sleep(0.01)  # Short sleep on error
        else:
            # Zero or minimal sleep to maintain timing precision
            remaining = next_frame_time - time.time()
            if remaining > 0.001:  # Only sleep if we have more than 1ms
                await asyncio.sleep(remaining)

async def send_position_updates(websocket, axis):
    """Send position updates at a controlled rate with caching."""
    update_count = 0
    last_position = None
    next_update_time = time.time()
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Only send updates at the specified interval
        if current_time >= next_update_time:
            next_update_time = current_time + EPOS_UPDATE_INTERVAL
            
            try:
                # Get current position
                position = await asyncio.to_thread(axis.getEPOS)
                
                # Only send if position has changed
                if position != last_position:
                    # Use cached JSON for better performance
                    message = get_cached_json("position_update", epos=position)
                    
                    await websocket.send(message)
                    update_count += 1
                    last_position = position
                    
                    # Debug logging less frequently
                    if update_count % 100 == 0:
                        logger.debug(f"Sent position update #{update_count}: {position}")
                        
            except Exception as e:
                logger.error(f"Error sending position update: {e}")
                
        else:
            # Minimal sleep to allow other tasks to run
            remaining = next_update_time - time.time()
            if remaining > 0.001:  # Only sleep if we have more than 1ms
                await asyncio.sleep(remaining)

async def health_checker(websocket):
    """Actively check connection health."""
    last_check_time = time.time()
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Only check at the specified interval
        if current_time - last_check_time >= HEALTH_CHECK_INTERVAL:
            last_check_time = current_time
            
            try:
                # Check if too much time has passed since last successful activity
                silence_duration = current_time - max(
                    last_successful_command_time,
                    last_ping_response_time
                )
                
                if silence_duration > MAX_SILENCE_DURATION:
                    logger.warning(f"Connection silence detected for {silence_duration:.1f}s")
                    
                    # Send a ping to check if connection is still alive
                    ping_message = get_cached_json(
                        "ping", 
                        timestamp=datetime.now().isoformat(),
                        uptime=time.time() - startup_time
                    )
                    
                    await websocket.send(ping_message)
                    logger.info("Sent health check ping")
                    
            except Exception as e:
                logger.error(f"Health check error: {e}")
                
        else:
            # Sleep until next check time
            await asyncio.sleep(0.1)  # Short sleep, health check isn't time-critical

async def periodic_maintenance(camera, axis, serial_device=None):
    """Perform periodic maintenance tasks to keep the system stable."""
    last_usb_flush = time.time()
    last_camera_flush = time.time()
    last_gc_run = time.time()
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Flush USB ports periodically
        if current_time - last_usb_flush >= USB_FLUSH_INTERVAL:
            last_usb_flush = current_time
            flush_usb_port(serial_device)
        
        # Flush camera buffers periodically
        if camera and current_time - last_camera_flush >= CAMERA_BUFFER_FLUSH_INTERVAL:
            last_camera_flush = current_time
            flush_camera_buffers(camera)
        
        # Force garbage collection periodically
        if current_time - last_gc_run >= GC_INTERVAL:
            last_gc_run = current_time
            optimize_memory_usage()
        
        # Sleep until next check - maintenance can sleep longer
        await asyncio.sleep(1.0)

# =================================================================
# CPU MONITORING AND ADAPTIVE PERFORMANCE
# =================================================================

def get_cpu_usage():
    """Get CPU usage percentage."""
    try:
        return float(os.popen("grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage}'").readline().strip())
    except Exception:
        return 0.0

async def monitor_cpu_usage():
    """Monitor CPU usage and log warnings if critical."""
    global cpu_usage
    
    next_check_time = time.time()
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Only check at the specified interval
        if current_time >= next_check_time:
            next_check_time = current_time + CPU_MONITOR_INTERVAL
            
            # Get CPU usage
            cpu_usage = get_cpu_usage()
            
            # Log CPU usage
            if cpu_usage > CPU_CRITICAL_THRESHOLD:
                logger.warning(f"CRITICAL CPU Usage: {cpu_usage:.1f}%")
                optimize_memory_usage()  # Force GC on critical usage
            elif cpu_usage > CPU_HIGH_THRESHOLD:
                logger.warning(f"HIGH CPU Usage: {cpu_usage:.1f}%")
            else:
                logger.info(f"CPU Usage: {cpu_usage:.1f}%")
        
        # Sleep until next check time - CPU monitoring can sleep longer
        await asyncio.sleep(1.0)

# =================================================================
# COMMAND PROCESSING OPTIMIZATION
# =================================================================

async def process_command(data, message_queue=None):
    """Handle commands with optimized processing."""
    try:
        command = data.get('command', '')
        
        # Process acceleration/deceleration command
        if command in ['acceleration', 'acce']:
            acce_value = data.get('acce')
            if acce_value is not None:
                set_acce_dece_params(acce_value=acce_value)
                response = {"type": "rpi_response", "status": "success"}
                response["message"] = f"Acceleration set to {acce_value}"
                await send_response(response, message_queue)
                
        elif command in ['deceleration', 'dece']:
            dece_value = data.get('dece')
            if dece_value is not None:
                set_acce_dece_params(dece_value=dece_value)
                response = {"type": "rpi_response", "status": "success"}
                response["message"] = f"Deceleration set to {dece_value}"
                await send_response(response, message_queue)
                
        # Update last successful command time
        global last_successful_command_time
        last_successful_command_time = time.time()
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing command: {e}")
        if message_queue:
            error_response = {
                "type": "rpi_response",
                "status": "error",
                "message": f"Command processing error: {str(e)}"
            }
            message_queue.add(json.dumps(error_response), high_priority=True)
        return False

async def send_response(response, message_queue=None):
    """Send a response with priority queueing if available."""
    try:
        if message_queue:
            message_queue.add(json.dumps(response), high_priority=True)
        return True
    except Exception as e:
        logger.error(f"Error sending response: {e}")
        return False

# =================================================================
# XERYON CONTROL FUNCTIONS
# =================================================================

def set_acce_dece_params(acce_value=None, dece_value=None):
    """Set acceleration and deceleration parameters with error handling."""
    global axis
    
    # Apply default values if none provided
    acce_value = acce_value if acce_value is not None else DEFAULT_ACCELERATION
    dece_value = dece_value if dece_value is not None else DEFAULT_DECELERATION
    
    try:
        # Try direct method first
        if axis and hasattr(axis, 'setAcce'):
            axis.setAcce(acce_value)
            logger.debug(f"Set acceleration to {acce_value}")
        elif axis and hasattr(axis, 'sendCommand'):
            # Fall back to command method
            axis.sendCommand(f"ACCE={acce_value}")
            logger.debug(f"Set acceleration to {acce_value} via command")
            
        if axis and hasattr(axis, 'setDece'):
            axis.setDece(dece_value)
            logger.debug(f"Set deceleration to {dece_value}")
        elif axis and hasattr(axis, 'sendCommand'):
            # Fall back to command method
            axis.sendCommand(f"DECE={dece_value}")
            logger.debug(f"Set deceleration to {dece_value} via command")
            
        return True
        
    except Exception as e:
        logger.error(f"Error setting acce/dece parameters: {e}")
        return False

# =================================================================
# MAIN EXECUTION FUNCTIONS
# =================================================================

async def main():
    """Entry point with proper shutdown handling."""
    global shutdown_requested, last_successful_command_time, last_ping_response_time
    global cpu_usage, startup_time, axis
    
    startup_time = time.time()
    shutdown_requested = False
    last_successful_command_time = time.time()
    last_ping_response_time = time.time()
    cpu_usage = 0.0
    
    # Apply initial optimizations
    logger.info("Applying CPU optimizations for high performance...")
    set_cpu_governor("performance")  # Use performance governor for maximum CPU
    
    # Initialize variables
    camera = None
    axis = None
    serial_device = "/dev/ttyACM0"  # Default Xeryon controller path
    
    try:
        # Initialize hardware
        logger.info("Initializing camera with high-performance settings...")
        camera = initialize_optimized_camera()
        
        logger.info("Initializing Xeryon controller...")
        # Initialize your Xeryon controller here
        # axis = initialize_xeryon_controller()
        
        # Start background tasks
        cpu_monitor_task = asyncio.create_task(monitor_cpu_usage())
        maintenance_task = asyncio.create_task(periodic_maintenance(camera, axis, serial_device))
        
        logger.info("System initialized and ready for operation")
        
        # Main client logic would follow...
        # ...
        
        # Clean up
        logger.info("Shutting down...")
        shutdown_requested = True
        
        # Cancel all background tasks
        cpu_monitor_task.cancel()
        maintenance_task.cancel()
        
        # Close hardware
        if camera:
            if hasattr(camera, 'close'):
                camera.close()
            elif hasattr(camera, 'release'):
                camera.release()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Cleanup complete")

# Example of how to use this in your main RPi client
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")

# =================================================================
# INTEGRATION INSTRUCTIONS
# =================================================================
"""
To integrate this optimization script into your combined-rpi-client.py:

1. Copy the configuration constants to your script
2. Replace logging setup with BufferedHandler implementation
3. Add the performance optimization functions
4. Replace camera functions with the optimized versions
5. Add the USB and camera buffer flush functions
6. Replace WebSocket send functions with the optimized versions
7. Add the periodic maintenance task
8. Integrate CPU monitoring

Remember to keep the high-resolution and high-FPS settings intact as requested.
"""