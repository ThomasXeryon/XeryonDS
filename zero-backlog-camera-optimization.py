"""
ZERO BACKLOG CAMERA FRAME OPTIMIZATION

This module contains optimizations to achieve absolute zero backlog in camera frame delivery.
Apply these changes to the `send_camera_frames` function in your RPi client.
"""

async def send_camera_frames(websocket):
    """Send camera frames with extreme real-time optimization, ensuring absolutely zero backlog."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_frame_time = time.time()
    last_frame_size = 0
    
    # Pre-allocated buffer for image processing
    overlay_text = f"RPI: {STATION_ID}"
    # Configure a fixed quality setting based on network conditions
    # Use a lower fixed quality (55) to ensure frames are small and transmit quickly
    FIXED_QUALITY = 55
    
    logger.info("Starting zero-backlog camera frame sender task")

    # Set up threaded encoding with a dedicated executor
    jpeg_executor = ThreadPoolExecutor(max_workers=1)  # Single-threaded for consistent performance
    
    while not shutdown_requested:
        try:
            # Skip everything if not on RPi
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue
                
            # Skip if camera not available  
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.warning("Camera not available - attempting to initialize")
                initialize_camera()
                await asyncio.sleep(1)
                continue

            # EXTREME OPTIMIZATION: Immediately capture new frame
            # No sleeping before capture - always get the freshest frame possible
            
            try:
                # Direct capture with minimal overhead
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
                
                # Only add minimal overlay text - timestamp is costly
                frame_time = datetime.now().isoformat()
                id_string = f"{overlay_text} - {frame_count}"
                cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 0, 255), 2)
                            
                # Use fixed quality for encoding - no adaptive quality
                buffer = cv2.imencode('.jpg', frame, 
                                     [cv2.IMWRITE_JPEG_QUALITY, FIXED_QUALITY,
                                      cv2.IMWRITE_JPEG_OPTIMIZE, 0])[1]
                                      
                # Track frame size for monitoring
                last_frame_size = len(buffer)
                
                # Encode directly to base64 without async overhead
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                
                # Prepare and immediately send the message
                frame_data = {
                    "type": "camera_frame",
                    "rpiId": STATION_ID,
                    "frame": jpg_as_text,
                    "timestamp": frame_time,
                    "frameNumber": frame_count
                }
                
                # Send with no delay
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_successful_frame_time = time.time()
                last_frame_time = time.time()
                
                # Log only very occasionally
                if frame_count % 100 == 0:
                    elapsed = time.time() - last_frame_time
                    fps = 1.0 / max(elapsed, 0.001)
                    logger.debug(f"Frame stats: #{frame_count}, {last_frame_size/1024:.1f}KB, {fps:.1f}fps")
                
                # CRITICAL: Rate limiting
                # Only sleep a tiny amount to prevent CPU spinning
                # This is the only sleep in the entire loop
                await asyncio.sleep(MIN_SLEEP_DELAY)
                
            except Exception as e:
                # Just log and continue immediately, no sleeping on errors
                logger.error(f"Frame error: {str(e)}")
                
        except Exception as e:
            logger.error(f"Camera frame sender error: {str(e)}")
            # Minimal sleep on outer exception
            await asyncio.sleep(0.01)

# Flush camera buffers function to be called periodically from a separate task
async def flush_camera_buffers():
    """Periodically flush camera buffers to prevent stale frames."""
    global picam2
    
    while not shutdown_requested:
        try:
            if RUNNING_ON_RPI and picam2 and hasattr(picam2, 'started') and picam2.started:
                # Capture and discard a few frames to flush any buffered/stale data
                for _ in range(3):
                    try:
                        _ = picam2.capture_array("main")
                    except Exception as e:
                        logger.error(f"Error flushing camera buffer: {str(e)}")
                logger.debug("Camera buffers flushed")
            
            # Flush every 3 seconds
            await asyncio.sleep(3)
            
        except Exception as e:
            logger.error(f"Camera buffer flush error: {str(e)}")
            await asyncio.sleep(1)