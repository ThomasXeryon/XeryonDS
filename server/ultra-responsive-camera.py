async def send_camera_frames(websocket):
    """Ultra-responsive camera function that maintains high FPS during movement.
    Optimized to prevent FPS drop-off during actuator movement."""
    global picam2, last_successful_command_time, axis
    
    # Frame tracking
    frame_count = 0
    last_frame_time = time.time()
    
    # For command tracking
    last_command_time = 0
    
    logger.info("Starting ultra-responsive camera sender")
    
    # Use a smaller, dedicated thread pool for JPEG encoding
    jpeg_pool = ThreadPoolExecutor(max_workers=1)
    
    # Buffer management task
    async def aggressive_buffer_management():
        """Aggressively manage camera buffer to ensure freshness."""
        while not shutdown_requested:
            try:
                if RUNNING_ON_RPI and picam2 and hasattr(picam2, 'started') and picam2.started:
                    # Flush the camera buffer by capturing and discarding
                    try:
                        _ = picam2.capture_array("main")
                    except:
                        pass
                await asyncio.sleep(0.1)  # Check 10 times per second
            except:
                await asyncio.sleep(0.1)
    
    # Start buffer management task
    buffer_task = asyncio.create_task(aggressive_buffer_management())
    
    # Main frame sending loop
    while not shutdown_requested:
        try:
            # Skip if not on RPi
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue
            
            # Initialize camera if needed
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                initialize_camera()
                await asyncio.sleep(0.5)
                continue
            
            # CRITICAL: Absolute minimal sleep to allow other tasks to run
            # This maintains maximum possible FPS at all times
            await asyncio.sleep(0.0001)  # 0.1ms sleep - essentially no throttling
            
            # Check if a command was recently issued (within last 1 second)
            current_time = time.time()
            command_just_executed = (current_time - last_successful_command_time < 1.0)
            
            # Capture frame with buffer management
            try:
                # Always flush buffer during command execution for maximum responsiveness
                if command_just_executed:
                    # Discard frames to get freshest image
                    _ = picam2.capture_array("main")
                
                # Capture the frame we'll actually use
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
                capture_time = time.time()
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # Add frame counter text to EVERY frame
            frame_text = f"Frame: {frame_count}"
            cv2.putText(frame, frame_text, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Encode the JPEG - optimize for speed when movements are happening
            try:
                # Choose quality based on command activity
                # During commands, use lower quality for max speed
                quality = 30 if command_just_executed else JPEG_QUALITY
                
                # Use direct encoding for minimal latency
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    continue
                
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
            
            # Get current position when possible
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    position_data = epos
                    with position_lock:
                        current_position = epos
                except:
                    pass
            
            # Prepare the message
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Include position data if available
            if position_data is not None:
                frame_data["epos"] = position_data
            
            # Send with minimal timeout to prevent blocking
            try:
                # Use a shorter timeout during command execution
                timeout = 0.1 if command_just_executed else 0.2
                await asyncio.wait_for(
                    websocket.send(json.dumps(frame_data)),
                    timeout=timeout
                )
                
                frame_count += 1
                last_frame_time = time.time()
                
            except asyncio.TimeoutError:
                logger.warning("Frame send timeout")
            except Exception as e:
                logger.error(f"Send error: {e}")
                await asyncio.sleep(0.01)
            
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)
    
    # Clean up
    buffer_task.cancel()
    try:
        await buffer_task
    except asyncio.CancelledError:
        pass
    
    # Clean up thread pool
    jpeg_pool.shutdown(wait=False)