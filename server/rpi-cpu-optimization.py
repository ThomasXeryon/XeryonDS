"""
SIMPLE CPU OPTIMIZATION FOR RASPBERRY PI CLIENT

Essential optimizations to reduce CPU usage while maintaining high quality
camera streaming and sensor readings.
"""

import asyncio
import json
import time
import logging
import base64
import os
import sys
import subprocess
from datetime import datetime

# ==========================================
# SETTINGS
# ==========================================

# Camera settings - Keep high resolution as requested
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_FPS = 30
CAMERA_QUALITY = 50

# USB and Memory Management - Simple settings
USB_FLUSH_INTERVAL = 60  # Flush USB port every 60 seconds
CAMERA_BUFFER_FLUSH_INTERVAL = 30  # Flush camera buffer every 30 seconds

# ==========================================
# USB PORT AND CAMERA BUFFER MANAGEMENT
# ==========================================

def flush_usb_port(device_path="/dev/ttyACM0"):
    """Flush USB port buffers to prevent data buildup."""
    if not os.path.exists(device_path):
        return False
        
    try:
        import serial
        ser = serial.Serial(device_path, 115200, timeout=1)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.flush()
        ser.close()
        print(f"Flushed USB port: {device_path}")
        return True
    except Exception as e:
        print(f"Error flushing USB port: {e}")
        return False

def flush_camera_buffers(camera):
    """Clear camera buffers to prevent memory buildup."""
    if not camera:
        return False
        
    try:
        # For picamera2
        if hasattr(camera, 'capture_array'):
            for _ in range(3):
                camera.capture_array("main")
            print("Flushed Picamera2 buffers")
            return True
            
        # For OpenCV VideoCapture
        elif hasattr(camera, 'grab'):
            for _ in range(5):
                camera.grab()
            print("Flushed OpenCV camera buffers")
            return True
            
        return False
    except Exception as e:
        print(f"Error flushing camera buffers: {e}")
        return False

# ==========================================
# MAIN MAINTENANCE TASK
# ==========================================

async def run_maintenance(camera, serial_device="/dev/ttyACM0"):
    """Periodically flush USB port and camera buffers."""
    last_usb_flush = time.time()
    last_camera_flush = time.time()
    
    while True:
        try:
            current_time = time.time()
            
            # USB port flushing
            if current_time - last_usb_flush >= USB_FLUSH_INTERVAL:
                flush_usb_port(serial_device)
                last_usb_flush = current_time
                
            # Camera buffer flushing
            if camera and current_time - last_camera_flush >= CAMERA_BUFFER_FLUSH_INTERVAL:
                flush_camera_buffers(camera)
                last_camera_flush = current_time
                
            # Sleep before next check
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"Maintenance error: {e}")
            await asyncio.sleep(10)  # Longer sleep on error

# ==========================================
# MEMORY OPTIMIZATION
# ==========================================

def optimize_memory():
    """Force garbage collection to free up memory."""
    try:
        import gc
        gc.collect()
        print("Memory optimized via garbage collection")
        return True
    except Exception as e:
        print(f"Memory optimization error: {e}")
        return False

# ==========================================
# USAGE EXAMPLE
# ==========================================

# Add these lines to your main program:
#
# # Start maintenance task
# maintenance_task = asyncio.create_task(run_maintenance(camera))
#
# # Cleanup at shutdown
# maintenance_task.cancel()