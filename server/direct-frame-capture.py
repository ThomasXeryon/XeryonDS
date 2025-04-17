async def send_camera_frames(websocket):
    """Send camera frames with ultra-real-time performance - no backlog allowed."""
    global picam2, last_successful_frame_time
    
    # Keep track of processing state
    frame_count = 0
    last_camera_capture = time.time()
    last_successful_send = time.time()
    frame_interval = 1.0 / TARGET_FPS
    
    # Buffer management
    last_buffer_flush = time.time()
    BUFFER_FLUSH_INTERVAL = 1.0  # Flush camera buffers every 1 second
    
    logger.info(f"Starting ultra-low-latency camera sender (JPEG quality: {JPEG_QUALITY})")
    
    while not shutdown_requested:
        try:
            # Skip simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(frame_interval)
                frame_count += 1
                continue
                
            # Initialize camera if needed
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.warning("Camera not available - initializing")
                initialize_camera()
                await asyncio.sleep(1)
                continue
            
            # CRITICAL OPTIMIZATION: Flush camera buffers periodically
            # This prevents frames from accumulating in the camera's internal buffer
            current_time = time.time()
            if current_time - last_buffer_flush > BUFFER_FLUSH_INTERVAL:
                # Flush by capturing and discarding frames
                for _ in range(3):
                    try:
                        _ = picam2.capture_array("main")
                    except:
                        pass
                last_buffer_flush = current_time
                
            # ZERO DELAY CAPTURE: Direct capture without any sleep or throttling
            # This ensures we always get the very latest frame from the camera
            try:
                # Skip awaiting - capture directly in this thread
                rgb_array = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
                last_camera_capture = time.time()
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                # Minimal sleep on error to avoid CPU thrashing
                await asyncio.sleep(0.01)
                continue
                
            # Skip image overlay and enhancement to reduce processing time
            
            # ULTRA-FAST ENCODING: Direct encode without async overhead
            try:
                # Use lowest viable quality to minimize network delay (40 is a good balance)
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, 40]
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    continue
                    
                # Fast base64 encoding
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Encoding error: {e}")
                continue
                
            # Try to include position data directly to eliminate need for separate messages
            position_data = None
            if RUNNING_ON_RPI and axis:
                try:
                    # Get position without async (direct call)
                    epos = axis.getEPOS()
                    position_data = epos
                    # Update tracked position
                    with position_lock:
                        current_position = epos
                except:
                    pass
                    
            # Create minimal message - only essential data
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": datetime.now().isoformat(),
                "frameNumber": frame_count
            }
            
            # Add position if available
            if position_data is not None:
                frame_data["epos"] = position_data
                
            # FAST SEND: No waiting, just fire and forget
            try:
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                last_successful_frame_time = time.time()
                last_successful_send = time.time()
                
                # Log only periodically to reduce overhead
                if frame_count % 100 == 0:
                    logger.info(f"Sent frame #{frame_count} - latency: {(time.time() - last_camera_capture)*1000:.1f}ms")
            except Exception as e:
                logger.error(f"Send error: {e}")
                
            # CRITICAL: Add a very tiny sleep to yield control and prevent CPU lock
            # This is essential for overall system stability
            await asyncio.sleep(0.001)  # 1ms is enough to yield without delay
            
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            # Brief recovery pause
            await asyncio.sleep(0.1)