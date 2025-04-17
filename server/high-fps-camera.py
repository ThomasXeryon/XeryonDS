async def send_camera_frames(websocket):
    """High-FPS camera function with minimal lag and consistent text overlay."""
    global picam2, last_successful_command_time
    
    # Frame tracking
    frame_count = 0
    last_frame_time = time.time()
    
    # For camera buffer management
    last_buffer_flush = 0
    
    # For tracking active commands
    command_active = False
    command_start_time = 0
    
    logger.info("Starting high-FPS camera sender")
    
    # Create separate buffer flushing task that always runs
    async def continuous_buffer_flush():
        """Continuously flush camera buffers in the background to prevent buildup."""
        while not shutdown_requested:
            try:
                # Only try to flush if we have a camera and not actively sending a frame
                if RUNNING_ON_RPI and picam2 and hasattr(picam2, 'started') and picam2.started:
                    # Capture and discard to flush buffer
                    try:
                        _ = picam2.capture_array("main")
                    except:
                        pass
                # Run this check frequently
                await asyncio.sleep(0.2)  # 5 times per second
            except:
                await asyncio.sleep(0.2)
                
    # Start the buffer flushing task
    buffer_flush_task = asyncio.create_task(continuous_buffer_flush())
    
    # Create a background task to watch for new commands
    async def command_monitor():
        """Monitor for new commands and trigger immediate frame capture."""
        nonlocal command_active, command_start_time
        last_checked_command_time = 0
        
        while not shutdown_requested:
            try:
                current_time = time.time()
                # Check if we have a new command (comparing to our last checked time)
                if last_successful_command_time > last_checked_command_time:
                    # New command detected
                    command_active = True
                    command_start_time = last_successful_command_time
                    last_checked_command_time = last_successful_command_time
                    logger.debug(f"New command detected at {command_start_time}")
                
                # Check if command is still active (consider it active for 1 second)
                if command_active and (current_time - command_start_time > 1.0):
                    command_active = False
                    
                await asyncio.sleep(0.01)  # Check frequently but not too often
            except:
                await asyncio.sleep(0.05)
    
    # Start the command monitor
    command_monitor_task = asyncio.create_task(command_monitor())
    
    # Main frame sending loop
    while not shutdown_requested:
        try:
            # Skip simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue
                
            # Make sure we have a camera
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                initialize_camera()
                await asyncio.sleep(0.5)
                continue
                
            current_time = time.time()
            
            # *** ALWAYS HIGH FPS ***
            # Only take a tiny sleep to prevent CPU overload but maintain high FPS
            await asyncio.sleep(0.001)  # 1ms minimum sleep - allows for ~1000 FPS theoretical max
            
            # Capture a fresh frame - WITH NO BUFFER
            try:
                # If command is active, aggressively flush the buffer first
                if command_active:
                    # Capture and discard multiple frames to flush buffer during commands
                    for _ in range(5):  # Discard multiple frames to get newest image
                        _ = picam2.capture_array("main")
                
                # Now capture the frame we'll actually use
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
                last_frame_time = time.time() 
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # *** ALWAYS ADD TEXT OVERLAY ***
            # Add frame number and timestamp to every frame
            frame_time = datetime.now().isoformat()
            cv2.putText(frame, f"Frame: {frame_count}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Add command indicator if active
            if command_active:
                command_age = (time.time() - command_start_time) * 1000
                cv2.putText(frame, f"CMD: {command_age:.0f}ms", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Use fast encoding always for high FPS
            try:
                # Always use fast encoding for consistent high FPS
                # Balance quality and speed - 40 is a good middle ground
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, 40]
                
                # Direct encoding - no async to minimize latency
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    continue
                    
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
            
            # Add position data when possible
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    position_data = epos
                    with position_lock:
                        current_position = epos
                except:
                    pass
            
            # Prepare the message with minimal data
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            if position_data is not None:
                frame_data["epos"] = position_data
                
            # During commands, add indicator this is a high-priority frame
            if command_active:
                frame_data["priority"] = "high"
                frame_data["commandActive"] = True
                frame_data["commandDelay"] = (time.time() - command_start_time) * 1000
            
            # Send the frame with appropriate timeout
            try:
                # Use a reasonable timeout that won't block forever
                # but still allows for high FPS
                await asyncio.wait_for(
                    websocket.send(json.dumps(frame_data)),
                    timeout=0.2  # 200ms timeout is reasonable
                )
                
                frame_count += 1
                
            except asyncio.TimeoutError:
                logger.warning("Frame send timeout")
            except Exception as e:
                logger.error(f"Send error: {e}")
                await asyncio.sleep(0.01)
            
            # Minimal yield to allow other tasks to run
            await asyncio.sleep(0.001)
            
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)
    
    # Clean up background tasks
    buffer_flush_task.cancel()
    command_monitor_task.cancel()
    try:
        await buffer_flush_task
        await command_monitor_task
    except asyncio.CancelledError:
        pass