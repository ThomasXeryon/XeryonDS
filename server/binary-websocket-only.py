#!/usr/bin/env python3
"""
Binary WebSocket Frame Implementation
- ONLY modifies the camera frame transmission to use binary WebSocket
- Leaves all controller code completely untouched
- Adds binary frame support with proper unsigned 32-bit integers
"""

import struct

# ===== BINARY WEBSOCKET CHANGES =====
# Add these constants to your existing script:

# Protocol configuration for binary frames
FRAME_HEADER_FORMAT = "<4sII"  # format: 4-char station ID, uint32 frame number, uint32 timestamp
FRAME_HEADER_SIZE = struct.calcsize(FRAME_HEADER_FORMAT)

# ===== CAMERA FRAME BINARY SENDER =====
# Replace your existing send_camera_frames function with this version:

async def send_camera_frames(websocket):
    """Send camera frames as binary WebSocket messages for maximum efficiency."""
    global picam2, last_successful_frame_time
    
    frame_count = 0
    last_frame_time = time.time()
    frame_backlog = 0
    
    logger.info("Starting binary camera frame sender task")
    
    while not shutdown_requested:
        try:
            # Regular buffer flush to prevent buildup
            current_time = time.time()
            if current_time - last_frame_time > 1.0:  # Flush every second
                if picam2 and hasattr(picam2, 'capture_array'):
                    try:
                        _ = picam2.capture_array("main")  # Capture and discard to clear buffer
                    except Exception as e:
                        logger.debug(f"Frame buffer flush error: {e}")
            
            # Skip rest of loop if in simulation mode
            if not RUNNING_ON_RPI:
                await asyncio.sleep(1.0 / 10.0)  # Simulate 10 FPS in non-RPi mode
                frame_count += 1
                continue
            
            # Skip if camera not available
            if not picam2 or not hasattr(picam2, 'started') or not picam2.started:
                logger.warning("Camera not available - attempting to initialize")
                initialize_camera()
                await asyncio.sleep(1)
                continue
            
            # Calculate timing for frame capture
            current_time = time.time()
            frame_interval = 1.0 / TARGET_FPS
            elapsed = current_time - last_frame_time
            
            # Skip frames if falling behind
            if elapsed > frame_interval * 2:
                frame_backlog += 1
                if frame_backlog % 10 == 0:
                    logger.debug(f"Frame sender falling behind (backlog: {frame_backlog}) - prioritizing freshness")
            else:
                frame_backlog = max(0, frame_backlog - 1)
                
                # Brief sleep if ahead of schedule
                if elapsed < frame_interval:
                    await asyncio.sleep(min(frame_interval - elapsed, 0.005))
            
            # Minimal sleep to prevent CPU hogging
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
            # Capture frame
            last_frame_time = time.time()
            try:
                rgb_buffer = picam2.capture_array("main")
                frame = cv2.cvtColor(rgb_buffer, cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # Add frame info overlay (if you had this before)
            if hasattr(cv2, 'putText'):
                frame_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                id_string = f"RPI: {STATION_ID} - Frame: {frame_count} - {frame_time}"
                cv2.putText(frame, id_string, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                            0.7, (0, 0, 255), 2)
                
                # Add position overlay (if you had this before)
                with position_lock:
                    pos_str = f"Position: {current_position:.3f} mm"
                    cv2.putText(frame, pos_str, (10, 70), cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, (0, 0, 255), 2)
            
            # Adjust JPEG quality
            jpeg_quality = JPEG_QUALITY
            if frame_backlog > 5:
                jpeg_quality = max(30, JPEG_QUALITY - (frame_backlog // 5) * 10)
            
            # Encode JPEG
            try:
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality, 
                               cv2.IMWRITE_JPEG_OPTIMIZE, 1]
                success, buffer = cv2.imencode('.jpg', frame, encode_param)
                if not success:
                    raise RuntimeError("JPEG encoding failed")
                
                # Create binary frame header with unsigned 32-bit ints
                timestamp = int(time.time() * 1000) % 0xFFFFFFFF  # Ensure fits in uint32
                frame_num = frame_count % 0xFFFFFFFF              # Ensure fits in uint32
                
                # Pack the header
                header = struct.pack(FRAME_HEADER_FORMAT,
                                    STATION_ID.encode()[:4].ljust(4),  # Force 4 chars
                                    frame_num,
                                    timestamp)
                
                # Combine header and JPEG data
                binary_data = header + buffer.tobytes()
                
                # Send as binary WebSocket message
                await websocket.send(binary_data)
                
                frame_count += 1
                last_successful_frame_time = time.time()
                
                if frame_count % 100 == 0:
                    logger.info(f"Sent {frame_count} binary frames")
                
            except Exception as e:
                logger.error(f"Frame encoding or sending error: {e}")
                await asyncio.sleep(0.01)
                continue
            
            # Minimal sleep at end of transmission
            await asyncio.sleep(MIN_SLEEP_DELAY)
            
        except Exception as e:
            logger.error(f"Camera frame task error: {e}")
            await asyncio.sleep(0.5)