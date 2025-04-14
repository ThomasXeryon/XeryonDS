"""
EXTREME CPU OPTIMIZATION MEASURES FOR RASPBERRY PI CLIENT

This file contains targeted optimizations to drastically reduce CPU usage on the RPi.
Apply these changes to your combined-rpi-client.py file.

Main CPU issues:
1. OpenCV operations are very CPU intensive
2. Frequent camera frame captures with high resolution
3. Busy loops without sufficient sleep times
4. Base64 encoding of large images
5. JSON serialization overhead
"""

# =============================================
# OPTIMIZATION 1: REDUCE CAMERA RESOLUTION AND FRAMERATE
# =============================================

# Replace these values:
RESOLUTION_WIDTH = 1280  # Original value
RESOLUTION_HEIGHT = 720  # Original value
JPEG_QUALITY = 50       # Original value
TARGET_FPS = 15         # Original value

# With these reduced values:
RESOLUTION_WIDTH = 640   # HALF resolution width
RESOLUTION_HEIGHT = 360  # HALF resolution height
JPEG_QUALITY = 30        # Lower quality to save CPU (30% quality is sufficient for monitoring)
TARGET_FPS = 5           # Drastically reduce framerate to 5 FPS (massive CPU savings)
SKIP_FRAMES = 3          # Skip frames periodically to reduce processing load


# =============================================
# OPTIMIZATION 2: REDUCE CPU IN CAMERA PROCESSING
# =============================================

# Replace the camera frame sending function with this optimized version:

async def send_camera_frames(websocket):
    """Send camera frames in a background task with extreme CPU optimization."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_frame_time = time.time()
    frame_skip_counter = 0
    
    # Create a small font to reduce drawing time
    font_scale = 0.5  # Reduced from 0.7
    font_thickness = 1  # Reduced from 2
    
    while not shutdown_requested:
        try:
            # Check if camera is initialized
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.error("Camera not started, pausing frame sending")
                await asyncio.sleep(2)  # Sleep longer when camera not ready
                continue
            
            # Rate limit frame capture based on TARGET_FPS
            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time
            
            if elapsed < frame_interval:
                # Sleep until next frame is due
                await asyncio.sleep(frame_interval - elapsed + 0.01)  # Add 10ms buffer
                continue
            
            # Skip frames periodically to reduce CPU load
            frame_skip_counter += 1
            if frame_skip_counter % SKIP_FRAMES != 0:
                # Just send position update without image when skipping
                epos = await asyncio.to_thread(axis.getEPOS) if axis else 0.0
                position_only_data = {
                    "type": "position_update",
                    "rpiId": STATION_ID,
                    "epos": epos,
                    "timestamp": datetime.now().isoformat(),
                    "frameSkipped": True
                }
                await websocket.send(json.dumps(position_only_data))
                
                # Short sleep between messages
                await asyncio.sleep(0.01)
                continue
                
            # Update timing
            last_frame_time = time.time()
            
            # Capture frame with reduced processing
            rgb_buffer = picam2.capture_array("main")
            
            # Convert to BGR with lower CPU usage
            # Skip cv2.cvtColor and use simpler conversion if needed
            frame = rgb_buffer  # Use as-is to avoid conversion
            
            # Skip most text overlay to save CPU - just add minimal info
            if frame_count % 5 == 0:  # Only add text every 5th frame
                # Get timestamp for this frame (reduced precision)
                frame_time = datetime.now().strftime("%H:%M:%S")
                
                # Add minimal ID info using faster method
                id_string = f"RPI{STATION_ID}-{frame_count}"
                cv2.putText(frame, id_string, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 
                           font_scale, (0, 0, 255), font_thickness)
            
            # Encode with lowest CPU overhead
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            # Try to reuse buffers if possible
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            # Aggressively sleep to reduce CPU
            await asyncio.sleep(0.05)
            
            # Create and send the frame data with minimal fields
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": jpg_as_text,
                "frameNumber": frame_count
            }
            
            try:
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_successful_frame_time = time.time()
                
                # Only log occasionally
                if frame_count % 50 == 0:
                    logger.debug(f"Sent frame {frame_count}")
            except Exception as e:
                logger.error(f"Failed to send frame: {e}")
                await asyncio.sleep(1)  # Longer sleep on error
                
        except Exception as e:
            logger.error(f"Camera frame error: {str(e)}")
            await asyncio.sleep(2)  # Sleep longer on error
        
        # Add a significant sleep at the end of each loop iteration
        await asyncio.sleep(0.1)


# =============================================
# OPTIMIZATION 3: INCREASE ALL SLEEP DELAYS
# =============================================

# Replace this constant:
MIN_SLEEP_DELAY = 0.001  # Original 1ms

# With these more aggressive delays:
MIN_SLEEP_DELAY = 0.005  # 5ms minimum delay
NORMAL_SLEEP_DELAY = 0.02  # 20ms normal delay
ERROR_SLEEP_DELAY = 0.5  # 500ms error delay


# =============================================
# OPTIMIZATION 4: ADD YIELD POINTS THROUGHOUT CODE
# =============================================

# Add after every major CPU operation:
await asyncio.sleep(NORMAL_SLEEP_DELAY)

# Example:
if acce_value is not None or dece_value is not None:
    set_acce_dece_params(acce_value, dece_value)
    if acce_value is not None:
        response["acceleration"] = acce_value
    if dece_value is not None:
        response["deceleration"] = dece_value
    
    # Add sleep after CPU intensive operation
    await asyncio.sleep(NORMAL_SLEEP_DELAY)


# =============================================
# OPTIMIZATION 5: REDUCE BACKGROUND TASK COUNT
# =============================================

# Combine position_updates with health_checker to reduce the number of running tasks

async def combined_background_tasks(websocket):
    """Combined position updates and health checks to reduce task overhead."""
    global axis, startup_time, last_successful_command_time
    
    last_epos = None
    last_health_check = time.time()
    last_update_time = time.time()
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            
            # POSITION UPDATES SECTION
            if axis and current_time - last_update_time >= EPOS_UPDATE_INTERVAL:
                last_update_time = current_time
                
                # Get current position
                epos = await asyncio.to_thread(axis.getEPOS)
                
                # Only send if position changed or every 1 second
                if last_epos != epos or current_time - last_update_time > 1.0:
                    position_data = {
                        "type": "position_update",
                        "rpiId": STATION_ID,
                        "epos": epos
                    }
                    
                    try:
                        await websocket.send(json.dumps(position_data))
                        last_epos = epos
                        last_successful_command_time = current_time
                    except Exception as e:
                        logger.error(f"Position update error: {e}")
            
            # HEALTH CHECK SECTION - run every health_check_interval
            if current_time - last_health_check >= health_check_interval:
                last_health_check = current_time
                
                # Check system health
                command_silence = current_time - last_successful_command_time
                frame_silence = current_time - last_successful_frame_time
                ping_silence = current_time - last_ping_response_time
                
                # Only log health status occasionally
                if random.random() < 0.2:  # Only log 20% of the time
                    logger.debug(f"Health: cmd={command_silence:.1f}s, frame={frame_silence:.1f}s")
                
                # Send a health check ping only if needed
                if ping_silence > health_check_interval * 2:
                    ping_data = {
                        "type": "health_check",
                        "timestamp": datetime.now().isoformat(),
                        "rpiId": STATION_ID,
                        "uptime": current_time - startup_time
                    }
                    
                    try:
                        await websocket.send(json.dumps(ping_data))
                    except Exception:
                        pass  # Ignore health check errors
            
            # Sleep between checks to reduce CPU
            await asyncio.sleep(NORMAL_SLEEP_DELAY)
            
        except Exception as e:
            logger.error(f"Background task error: {str(e)}")
            await asyncio.sleep(ERROR_SLEEP_DELAY)


# =============================================
# OPTIMIZATION 6: MODIFY MAIN FUNCTION TO USE FEWER TASKS
# =============================================

# In the rpi_client function, reduce the number of tasks:

# Replace this:
frame_task = asyncio.create_task(send_camera_frames(websocket))
position_task = asyncio.create_task(send_position_updates(websocket))
health_task = asyncio.create_task(health_checker(websocket))

# With:
frame_task = asyncio.create_task(send_camera_frames(websocket))
background_task = asyncio.create_task(combined_background_tasks(websocket))

# And when canceling tasks:
frame_task.cancel()
background_task.cancel()


# =============================================
# OPTIMIZATION 7: ADD CPU GOVERNOR MANAGEMENT
# =============================================

# Add this function to manage the CPU governor for better power/performance balance

def set_cpu_governor(governor="ondemand"):
    """Set the CPU governor to control power/performance balance.
    
    Governors:
    - performance: Maximum performance, highest power usage
    - powersave: Maximum power savings, lowest performance
    - ondemand: Scales based on load (default)
    - conservative: More gradual scaling than ondemand
    """
    try:
        # Get number of CPU cores
        cpu_count = os.cpu_count()
        
        # Set governor for each CPU
        for cpu in range(cpu_count):
            governor_path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
            if os.path.exists(governor_path):
                with open(governor_path, 'w') as f:
                    f.write(governor)
                    
        logger.info(f"CPU governor set to {governor}")
        return True
    except Exception as e:
        logger.error(f"Failed to set CPU governor: {e}")
        return False

# Call this at startup:
set_cpu_governor("ondemand")  # Balance power and performance


# =============================================
# OPTIMIZATION 8: ADD CPU MONITORING AND THROTTLING
# =============================================

# Replace the CPU monitoring function with this more effective version:

async def monitor_cpu_usage():
    """Monitor CPU usage and dynamically adjust processing behavior."""
    global MIN_SLEEP_DELAY, TARGET_FPS, SKIP_FRAMES
    
    original_delay = MIN_SLEEP_DELAY
    original_fps = TARGET_FPS
    original_skip = SKIP_FRAMES
    
    high_cpu_count = 0
    
    while not shutdown_requested:
        try:
            # Get CPU usage percentage
            cpu_percent = 0
            try:
                with open('/proc/stat', 'r') as f:
                    fields = [float(column) for column in f.readline().strip().split()[1:]]
                    idle, total = fields[3], sum(fields)
                
                await asyncio.sleep(0.5)  # Measure over 0.5 second
                
                with open('/proc/stat', 'r') as f:
                    fields = [float(column) for column in f.readline().strip().split()[1:]]
                    idle_new, total_new = fields[3], sum(fields)
                
                idle_delta, total_delta = idle_new - idle, total_new - total
                cpu_percent = 100.0 * (1.0 - idle_delta / total_delta)
            except Exception:
                cpu_percent = 0  # Default if can't measure
            
            # Get temperature
            temp = 50.0  # Default if can't measure
            try:
                temp_output = subprocess.check_output(['vcgencmd', 'measure_temp']).decode()
                temp = float(temp_output.replace('temp=', '').replace('\'C', ''))
            except Exception:
                pass
                
            # Log system status
            logger.info(f"System: CPU {cpu_percent:.1f}%, Temp {temp:.1f}°C")
            
            # Adjust parameters based on CPU load and temperature
            if cpu_percent > 80 or temp > 75:  # High load or high temperature
                high_cpu_count += 1
                
                if high_cpu_count >= 3:  # Only throttle after persistent high load
                    # Aggressive throttling
                    MIN_SLEEP_DELAY = 0.01  # 10ms
                    TARGET_FPS = max(2, original_fps // 3)  # Reduce to 1/3 but minimum 2 FPS
                    SKIP_FRAMES = original_skip * 2  # Double frame skipping
                    
                    # Set CPU governor to powersave mode
                    set_cpu_governor("powersave")
                    
                    logger.warning(f"CPU throttling enabled: {cpu_percent:.1f}% CPU, {temp:.1f}°C")
            elif cpu_percent > 60 or temp > 65:  # Moderate load
                high_cpu_count = max(1, high_cpu_count)  # Keep at least some count
                
                # Moderate throttling
                MIN_SLEEP_DELAY = 0.007  # 7ms
                TARGET_FPS = max(3, original_fps // 2)  # Reduce to half but minimum 3 FPS
                SKIP_FRAMES = original_skip + 1  # Increase frame skipping
                
                # Set CPU governor to conservative mode
                set_cpu_governor("conservative")
                
                logger.info(f"CPU moderately throttled: {cpu_percent:.1f}% CPU, {temp:.1f}°C")
            else:  # Normal load
                high_cpu_count = max(0, high_cpu_count - 1)
                
                if high_cpu_count == 0:
                    # Restore original parameters
                    MIN_SLEEP_DELAY = original_delay
                    TARGET_FPS = original_fps
                    SKIP_FRAMES = original_skip
                    
                    # Set CPU governor back to ondemand
                    set_cpu_governor("ondemand")
                    
                    logger.info(f"CPU throttling disabled: {cpu_percent:.1f}% CPU, {temp:.1f}°C")
            
            # Wait before checking again - longer interval to save CPU
            await asyncio.sleep(CPU_MONITOR_INTERVAL)
            
        except Exception as e:
            logger.error(f"CPU monitoring error: {e}")
            await asyncio.sleep(CPU_MONITOR_INTERVAL)


# =============================================
# OPTIMIZATION 9: REDUCE JSON PROCESSING OVERHEAD
# =============================================

# Use faster JSON serialization - add these imports
try:
    import ujson as json  # Much faster JSON processing
except ImportError:
    import json

# Create a cache for frequently sent messages
message_cache = {}

def get_cached_json(message_type, **kwargs):
    """Get cached JSON string for frequently sent message types."""
    global message_cache
    
    # Only cache certain immutable messages
    if message_type not in ["pong", "heartbeat_response"]:
        return json.dumps(dict(type=message_type, **kwargs))
    
    # Create cache key from all values
    cache_key = message_type + str(hash(frozenset(kwargs.items())))
    
    if cache_key not in message_cache:
        message_cache[cache_key] = json.dumps(dict(type=message_type, **kwargs))
        
        # Limit cache size
        if len(message_cache) > 100:
            # Remove a random key
            random_key = next(iter(message_cache))
            del message_cache[random_key]
    
    return message_cache[cache_key]


# =============================================
# OPTIMIZATION 10: REDUCE LOGGING OVERHEAD
# =============================================

# Configure logging to be less verbose and use buffered I/O
class BufferedHandler(logging.StreamHandler):
    """A logging handler that buffers records before flushing to reduce I/O."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buffer = []
        self.buffer_size = 10
        self.last_flush = time.time()
        self.flush_interval = 5  # seconds
    
    def emit(self, record):
        self.buffer.append(record)
        
        current_time = time.time()
        if len(self.buffer) >= self.buffer_size or current_time - self.last_flush >= self.flush_interval:
            self.flush()
            self.last_flush = current_time
    
    def flush(self):
        self.acquire()
        try:
            if self.buffer:
                for record in self.buffer:
                    super().emit(record)
                self.buffer = []
                super().flush()
        finally:
            self.release()

# Replace the standard logging setup with:
def setup_optimized_logging():
    """Set up logging optimized for lower CPU usage."""
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create buffered handler
    handler = BufferedHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # Set levels
    root_logger.setLevel(logging.INFO)  # Reduce from DEBUG to INFO
    handler.setLevel(logging.INFO)
    
    # Add handler
    root_logger.addHandler(handler)
    
    return logging.getLogger(__name__)

# Replace logger initialization with:
logger = setup_optimized_logging()