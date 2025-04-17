async def send_camera_frames(websocket):
    """Camera function optimized for minimal command-to-visual-feedback latency.
    Prioritizes showing movement changes immediately after commands are executed."""
    global picam2, last_successful_command_time, axis
    
    frame_count = 0
    last_command_check = time.time()
    
    # Latency measurement
    command_timestamps = {}  # Store timestamps of recent commands
    MAX_COMMAND_HISTORY = 10  # Keep track of last 10 commands
    
    logger.info("Starting minimal-latency camera sender")
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            
            # Handle simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / TARGET_FPS)
                frame_count += 1
                continue
                
            # Initialize camera if needed
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                initialize_camera()
                await asyncio.sleep(1)
                continue
                
            # *** CRITICAL FEATURE: DETECT COMMAND EXECUTION ***
            # If a command was recently executed, we need to send frames ASAP
            # to show the movement as quickly as possible
            command_just_executed = False
            time_since_last_command = current_time - last_successful_command_time
            
            if time_since_last_command < 1.0:  # Command in last 1 second
                command_just_executed = True
                # Store timestamp for this command if it's new
                command_id = int(last_successful_command_time * 1000)  # Millisecond precision ID
                if command_id not in command_timestamps:
                    command_timestamps[command_id] = last_successful_command_time
                    # Keep only recent commands
                    if len(command_timestamps) > MAX_COMMAND_HISTORY:
                        oldest_key = min(command_timestamps.keys())
                        del command_timestamps[oldest_key]
            
            # *** ADAPTIVE FRAMERATE BASED ON MOVEMENT ***
            # Send frames much faster right after a command, slower during idle periods
            if command_just_executed:
                # Maximum frame rate after a command (use minimal sleep)
                await asyncio.sleep(0.001)  # 1ms minimal sleep for CPU yield
            else:
                # Reduced frame rate during idle periods to save bandwidth
                await asyncio.sleep(0.05)  # ~20 FPS when idle
            
            # *** GUARANTEED FRESH FRAME ***
            # Flush stale frames after a command to ensure we see movement start
            try:
                if command_just_executed:
                    # After a command, flush any buffered frames to get the newest image
                    for _ in range(3):
                        _ = picam2.capture_array("main")  # Discard frames to flush buffer
                
                # Capture the frame we'll actually send
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
                capture_time = time.time()  # When was this frame taken
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # Apply minimal overlay to reduce processing time
            # Show command execution timing for debugging
            if command_just_executed:
                # Visual indicator that this frame is right after a command
                command_delay = (capture_time - last_successful_command_time) * 1000
                cv2.putText(frame, f"CMD: {command_delay:.0f}ms ago", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # *** OPTIMIZE ENCODING SPEED AFTER COMMANDS ***
            # Use fastest encoding settings right after a command
            try:
                if command_just_executed:
                    # Use lowest viable quality after command for fastest delivery
                    quality = 30  # Lower quality for faster delivery after command
                else:
                    # Standard quality during idle periods
                    quality = JPEG_QUALITY
                    
                # Speed-optimized encoding parameters
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    continue
                    
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
            
            # Always include current position to minimize position-to-visual lag
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    position_data = epos
                    with position_lock:
                        current_position = epos
                except:
                    pass
            
            # Prepare message with command timing information
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Include position data and command timing data
            if position_data is not None:
                frame_data["epos"] = position_data
                
            if command_just_executed:
                frame_data["commandDelay"] = (capture_time - last_successful_command_time) * 1000
                
            # *** PRIORITIZED SENDING AFTER COMMANDS ***
            try:
                # After commands, use an even shorter timeout for sending
                timeout = 0.2 if command_just_executed else 0.5
                await asyncio.wait_for(
                    websocket.send(json.dumps(frame_data)),
                    timeout=timeout
                )
                
                frame_count += 1
                last_successful_frame_time = time.time()
                
                # Log only when needed
                if command_just_executed and frame_count % 5 == 0:
                    visual_feedback_latency = (time.time() - last_successful_command_time) * 1000
                    logger.info(f"Visual feedback latency: {visual_feedback_latency:.1f}ms after command")
                    
            except asyncio.TimeoutError:
                if command_just_executed:
                    logger.warning("Frame send timeout after command!")
            except Exception as e:
                logger.error(f"Send error: {e}")
                
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)