"""
Zero-Backlog Camera Frame Sender Function
- Ultra-low latency: Sends only the most recent frame with zero waiting
- Aggressive frame skipping: Drops frames when behind to ensure real-time display
- Direct capture to send pipeline: Minimizes buffer copies and processing
- Dynamic quality adjustment: Reduces quality under load to maintain real-time performance
"""

async def send_camera_frames(websocket):
    """Zero-backlog camera frame sender with absolute priority on freshness."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_frame_time = time.time()
    last_send_time = time.time()
    min_frame_interval = 1.0 / TARGET_FPS  # Target FPS timing
    last_flush_time = time.time()
    
    # Frame drop tracking
    frames_captured = 0
    frames_sent = 0
    
    logger.info("Starting zero-backlog camera frame sender")
    
    while not shutdown_requested:
        try:
            # Check if camera is available
            if not RUNNING_ON_RPI:
                # Simulation mode
                await asyncio.sleep(min_frame_interval)
                frame_count += 1
                continue
                
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.warning("Camera not available - attempting to initialize")
                initialize_camera()
                await asyncio.sleep(1)
                continue
                
            # OPTIMIZATION: Check if we should capture a new frame
            # We'll only capture if enough time has passed since last frame
            current_time = time.time()
            time_since_last_frame = current_time - last_frame_time
            time_since_last_send = current_time - last_send_time
            
            # *** REAL-TIME PRIORITY: Flush old frames on heavy backlog ***
            # If more than 2 frame intervals have passed since last successful send,
            # we're falling behind and should prioritize getting the newest frame out
            if time_since_last_send > min_frame_interval * 2:
                # Aggressive camera buffer flush every 2 seconds if falling behind
                if current_time - last_flush_time > 2.0:
                    # Flush the camera buffers by capturing multiple frames rapidly and discarding them
                    if RUNNING_ON_RPI and picam2:
                        try:
                            # Capture and discard several frames to clear any buffered frames
                            for _ in range(3):
                                _ = picam2.capture_array("main")
                            logger.debug("Flushed camera buffers to reduce latency")
                            last_flush_time = current_time
                        except Exception as e:
                            logger.error(f"Error flushing camera buffers: {e}")
            
            # Take absolute minimal sleep to prevent CPU hogging
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
            # *** ZERO-WAIT CAPTURE: Get the latest frame as quickly as possible ***
            # Capture frame with minimal error handling
            frames_captured += 1
            last_frame_time = time.time()
            
            try:
                # Capture frame directly
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
                
            # Get timestamp and add minimal overlay
            frame_time = datetime.now().isoformat()
            id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time[-12:-1]}"
            cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # *** ADAPTIVE QUALITY: Adjust JPEG quality based on load ***
            # Calculate how far behind we are from real-time
            latency_factor = max(1.0, time_since_last_send / min_frame_interval)
            
            # Select quality based on how far behind we are
            # Lower quality = faster encoding = lower latency
            if latency_factor > 5.0:  # Severely behind, use lowest quality
                jpeg_quality = 30  
            elif latency_factor > 3.0:  # Moderately behind
                jpeg_quality = 40
            elif latency_factor > 2.0:  # Slightly behind
                jpeg_quality = 50
            else:  # On time or close to it
                jpeg_quality = JPEG_QUALITY
                
            # *** DIRECT ENCODING: Optimize JPEG encoding for speed over quality ***
            # Use the fastest encoding settings when behind
            if latency_factor > 2.0:
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
            else:
                encode_param = [
                    cv2.IMWRITE_JPEG_QUALITY, jpeg_quality,
                    cv2.IMWRITE_JPEG_OPTIMIZE, 1,
                    cv2.IMWRITE_JPEG_PROGRESSIVE, 0  # Progressive is slower but nicer
                ]
                
            # Encode directly (no async - more immediate)
            try:
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    logger.error("JPEG encoding failed")
                    continue
                    
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.error(f"Frame encoding error: {e}")
                await asyncio.sleep(0.01)
                continue
                
            # *** OPTIMIZED MESSAGE DATA: Minimize JSON overhead ***
            # Get current position directly if available (no waiting for getEPOS)
            epos = None
            if RUNNING_ON_RPI and axis:
                try:
                    epos = axis.getEPOS()  # Get position without async delay
                except:
                    pass
                    
            # Prepare and send message with minimal data
            frame_data = {
                "type": "camera_frame",
                "rpiId": STATION_ID,
                "frame": f"data:image/jpeg;base64,{jpg_as_text}",
                "timestamp": frame_time,
                "frameNumber": frame_count
            }
            
            # Add position data if available to eliminate need for separate position messages
            if epos is not None:
                frame_data["epos"] = epos
                # Update tracked position
                with position_lock:
                    current_position = epos
                    
            # *** ZERO-DELAY SEND: Send frame immediately ***
            try:
                # Send with minimal added overhead
                await websocket.send(json.dumps(frame_data))
                frame_count += 1
                frames_sent += 1
                last_successful_frame_time = time.time()
                last_send_time = time.time()
                
                # Log only occasionally to reduce overhead
                if frame_count % 100 == 0:
                    drop_rate = 100 * (1 - (frames_sent / frames_captured)) if frames_captured > 0 else 0
                    logger.info(f"Frame stats: captured={frames_captured}, sent={frames_sent}, drop_rate={drop_rate:.1f}%, quality={jpeg_quality}")
                    
            except Exception as e:
                logger.error(f"Frame send error: {e}")
                await asyncio.sleep(0.01)
                
        except Exception as e:
            logger.error(f"Camera sender error: {str(e)}")
            await asyncio.sleep(0.1)
            
        # Absolute minimal delay
        await asyncio.sleep(MIN_SLEEP_DELAY)