async def send_camera_frames(websocket):
    """Send camera frames with consistent timing and zero variable lag."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_capture_time = time.time()
    last_successful_send = time.time()
    consistent_interval = 1.0 / 15  # Target a consistent 15 FPS instead of 25
    last_gc_collect = time.time()
    
    # Create a heartbeat task to detect system slowdowns
    # This runs even when other operations may be blocked
    heartbeat_time = time.time()
    
    async def heartbeat_checker():
        nonlocal heartbeat_time
        while not shutdown_requested:
            heartbeat_time = time.time()
            await asyncio.sleep(0.1)  # Check every 100ms
    
    heartbeat_task = asyncio.create_task(heartbeat_checker())
    logger.info("Starting consistent frame rate camera sender")
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            
            # SYSTEM HEALTH CHECK: Detect if system is frozen
            # If heartbeat time is more than 0.5s old, system may be frozen
            if current_time - heartbeat_time > 0.5:
                logger.warning(f"System slowdown detected - heartbeat stalled for {current_time - heartbeat_time:.1f}s")
                # Skip any buffered frames by forcing a buffer flush
                if RUNNING_ON_RPI and picam2:
                    try:
                        for _ in range(5):  # Flush more aggressively
                            _ = picam2.capture_array("main")
                    except:
                        pass
            
            # GARBAGE COLLECTION: Regularly run garbage collection to prevent pauses
            # This prevents the GC from running at unpredictable times
            if current_time - last_gc_collect > 5.0:  # Every 5 seconds
                gc.collect()
                last_gc_collect = current_time
            
            # Handle simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(consistent_interval)
                frame_count += 1
                continue
                
            # Initialize camera if needed
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                initialize_camera()
                await asyncio.sleep(1)
                continue
                
            # CONSISTENT TIMING: Enforce consistent frame timing
            # Only capture new frames at a steady rate - don't exceed target FPS
            time_since_last_capture = current_time - last_capture_time
            if time_since_last_capture < consistent_interval:
                # Sleep precisely to maintain consistent frame rate
                await asyncio.sleep(consistent_interval - time_since_last_capture)
                
            # GUARANTEED FRESH FRAME: Flush stale frames and capture new one
            try:
                # Always flush at least one frame before capturing to discard any old frames
                _ = picam2.capture_array("main")  # Discard one frame to flush buffer
                
                # Now capture the fresh frame we actually want to send
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
                last_capture_time = time.time()
                capture_timestamp = datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error
                continue
                
            # Only add minimal timestamp to reduce processing time
            cv2.putText(frame, f"{frame_count}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # EFFICIENT ENCODING: Fixed quality and fast encoding options
            try:
                # Always use same quality settings for consistent performance
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, 40]  # Fixed quality
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    continue
                
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
                
            # Try to get position once for this frame
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()
                    position_data = epos
                    with position_lock:
                        current_position = epos
                except:
                    pass
            
            # Prepare message with consistent data format
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": capture_timestamp,  # Use capture time, not send time
                "frameNumber": frame_count,
                "captureTime": time.time() * 1000  # Millisecond precision timestamp
            }
            
            if position_data is not None:
                frame_data["epos"] = position_data
                
            # TIMELY DELIVERY: Send with timeout to prevent blocking
            try:
                # Use wait_for with timeout to avoid getting stuck on send
                await asyncio.wait_for(
                    websocket.send(json.dumps(frame_data)),
                    timeout=0.5  # Max 500ms to send frame before we consider it failed
                )
                
                frame_count += 1
                last_successful_frame_time = time.time()
                last_successful_send = time.time()
                
                # Track and log metrics occasionally
                if frame_count % 50 == 0:
                    latency = (time.time() - last_capture_time) * 1000
                    logger.info(f"Frame #{frame_count} - latency: {latency:.1f}ms")
            except asyncio.TimeoutError:
                logger.warning("Frame send timeout - network may be congested")
            except Exception as e:
                logger.error(f"Send error: {e}")
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)
    
    # Clean up heartbeat task
    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass