"""
BASIC RPI OPTIMIZATION WITH NO BULLSHIT

Simple and reliable optimizations with zero bloat.
Just the essential maintenance functions that actually work.
"""

import asyncio
import time
import os
import logging
import sys
import subprocess
import serial

# Configure logging - basic version that doesn't mess up anything
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger()

# USB flush interval
USB_FLUSH_INTERVAL = 60  # seconds
CAMERA_BUFFER_FLUSH_INTERVAL = 30  # seconds

# Shutdown flag
shutdown_flag = False

def flush_usb_port(device_path="/dev/ttyACM0"):
    """Flush USB port buffers to prevent data buildup."""
    try:
        if not os.path.exists(device_path):
            logger.info(f"Device {device_path} not found, skipping flush")
            return False
            
        ser = serial.Serial(device_path, 115200, timeout=1)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.flush()
        ser.close()
        logger.info(f"Flushed USB port: {device_path}")
        return True
    except Exception as e:
        logger.error(f"Error flushing USB port: {e}")
        return False

def flush_camera_buffers(camera):
    """Clear camera buffers to prevent memory buildup."""
    try:
        if not camera:
            return False
            
        # For picamera2
        if hasattr(camera, 'capture_array'):
            for _ in range(3):
                _ = camera.capture_array("main")
            logger.info("Flushed Picamera2 buffers")
            return True
            
        # For OpenCV VideoCapture
        elif hasattr(camera, 'grab'):
            for _ in range(5):
                camera.grab()
            logger.info("Flushed OpenCV camera buffers")
            return True
            
        logger.warning("Unknown camera type, couldn't flush buffers")
        return False
    except Exception as e:
        logger.error(f"Error flushing camera buffers: {e}")
        return False

def force_gc():
    """Force garbage collection."""
    try:
        import gc
        gc.collect()
        logger.info("Garbage collection performed")
        return True
    except Exception as e:
        logger.error(f"Error during garbage collection: {e}")
        return False

async def run_maintenance(camera, device_path="/dev/ttyACM0"):
    """Run maintenance functions periodically."""
    last_usb_flush = time.time()
    last_camera_flush = time.time()
    last_gc = time.time()
    
    logger.info("Starting maintenance task")
    
    while not shutdown_flag:
        try:
            current_time = time.time()
            
            # USB port flush
            if current_time - last_usb_flush >= USB_FLUSH_INTERVAL:
                flush_usb_port(device_path)
                last_usb_flush = current_time
                
            # Camera buffer flush
            if camera and current_time - last_camera_flush >= CAMERA_BUFFER_FLUSH_INTERVAL:
                flush_camera_buffers(camera)
                last_camera_flush = current_time
                
            # Garbage collection (less frequently)
            if current_time - last_gc >= 300:  # Every 5 minutes
                force_gc()
                last_gc = current_time
                
        except Exception as e:
            logger.error(f"Error in maintenance loop: {e}")
            
        # Sleep for a bit
        await asyncio.sleep(5)

async def main():
    """Main function."""
    global shutdown_flag
    
    camera = None
    maintenance_task = None
    
    try:
        logger.info("Starting system")
        
        # Your camera initialization code here
        # camera = initialize_camera()
        
        # Start maintenance task
        maintenance_task = asyncio.create_task(run_maintenance(camera))
        
        # Your main client code here
        # ...
        
        # Keep running until shutdown
        await asyncio.Future()
        
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # Cleanup
        shutdown_flag = True
        
        if maintenance_task:
            maintenance_task.cancel()
            
        if camera:
            if hasattr(camera, 'close'):
                camera.close()
            elif hasattr(camera, 'release'):
                camera.release()
                
        logger.info("Cleanup complete")

if __name__ == "__main__":
    asyncio.run(main())