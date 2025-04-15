# Xeryon Bulletproof Enhancements
# Add these improvements to your bulletproof-rpi-client.py file

# ===== SERIAL PORT ENHANCEMENT =====
# Replace your flush_serial_port function with this stronger version:
def flush_serial_port():
    """Aggressively flush serial port to avoid buffer issues with multi-layer approach."""
    if not RUNNING_ON_RPI:
        return True

    try:
        # First check if the COM port exists
        if not os.path.exists(COM_PORT):
            logger.warning(f"{COM_PORT} not found - attempting reset")
            try:
                # Try multiple USB reset methods
                subprocess.run(["usbreset", COM_PORT], check=False)
                time.sleep(1)
                subprocess.run(["sudo", "modprobe", "-r", "ftdi_sio"], check=False)
                time.sleep(0.5)
                subprocess.run(["sudo", "modprobe", "ftdi_sio"], check=False)
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to reset USB: {str(e)}")
                
            # Check again after reset attempt
            if not os.path.exists(COM_PORT):
                logger.error(f"{COM_PORT} still not available after reset")
                return False

        # Aggressively flush serial buffers with multiple methods
        try:
            # First try: Basic flush with explicit resource management
            with serial.Serial(COM_PORT, 115200, timeout=0.2) as ser:
                # Execute multiple flushes
                for _ in range(3):
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    time.sleep(0.01)
                
                # Send a carriage return to clear any pending commands
                ser.write(b'\r\n')
                time.sleep(0.05)
                
                # Read and discard any pending data
                _ = ser.read(ser.in_waiting or 1)
            
            # Second try: More aggressive open/close cycle
            time.sleep(0.1)
            ser = serial.Serial(COM_PORT, 115200, timeout=0.2)
            ser.close()
            time.sleep(0.1)
            ser = serial.Serial(COM_PORT, 115200, timeout=0.2)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.close()
            
            # Third try: Use lower-level file operations if available
            try:
                import termios
                import fcntl
                
                # Open port at file level
                fd = os.open(COM_PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                # Flush using termios
                termios.tcflush(fd, termios.TCIOFLUSH)
                # Close file descriptor
                os.close(fd)
            except (ImportError, AttributeError, OSError):
                # Skip this step if not on Linux or if it fails
                pass
                
        except Exception as inner_e:
            logger.error(f"Error during advanced serial flush: {str(inner_e)}")
            # Fall back to basic approach if the advanced one fails
            with serial.Serial(COM_PORT, 115200, timeout=0.5) as ser:
                ser.reset_input_buffer()
                ser.reset_output_buffer()

        logger.debug(f"Serial port {COM_PORT} flushed successfully using multi-layer approach")
        return True
    except Exception as e:
        logger.error(f"Error flushing serial port: {str(e)}")
        global serial_error_count
        serial_error_count += 1
        return False

# ===== COMMAND TIMEOUT ENHANCEMENT =====
# Add a timeout mechanism for Xeryon commands:
async def execute_with_timeout(func, *args, timeout=5.0):
    """Execute a function with a timeout and proper cleanup."""
    try:
        # Use wait_for to add a timeout to the thread execution
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Command timeout after {timeout}s: {func.__name__}({args})")
        
        # Force a serial port flush on timeout to clear any stuck commands
        flush_serial_port()
        
        # Re-enable the controller after timeout
        try:
            if axis:
                axis.sendCommand("ENBL=1")
        except:
            pass
        
        raise TimeoutError(f"Command {func.__name__} timed out after {timeout}s")

# ===== THERMAL ERROR RECOVERY ENHANCEMENT =====
# Replace your simple thermal error recovery with this more robust version:
async def recover_from_thermal_error():
    """Comprehensive recovery from thermal protection errors."""
    global thermal_error_count, axis, controller
    
    logger.warning(f"Attempting recovery from thermal error (count: {thermal_error_count})")
    
    # First try: Basic enable command
    try:
        if axis:
            axis.sendCommand("ENBL=1")
            time.sleep(0.1)
            logger.debug("Basic thermal recovery step 1: ENBL=1 sent")
    except Exception as e:
        logger.error(f"Basic thermal recovery failed: {str(e)}")
    
    # Second try: Check if that worked
    try:
        if axis:
            response = axis.sendCommand("ENBL?")
            logger.debug(f"Enable status: {response}")
            if "1" not in str(response):
                # Not enabled yet, try again with delay
                time.sleep(0.5)
                axis.sendCommand("ENBL=1")
                logger.debug("Basic thermal recovery step 2: Second ENBL=1 sent after delay")
    except Exception as e:
        logger.error(f"Status check failed: {str(e)}")
    
    # If we've had multiple thermal errors, do a more aggressive recovery
    if thermal_error_count > 2:
        logger.warning("Multiple thermal errors detected, performing aggressive recovery")
        
        # Aggressive approach: Reset controller
        try:
            if controller:
                controller.stop()
                time.sleep(1.0)
                
                # Aggressively flush the serial port
                flush_serial_port()
                
                # Reinitialize
                controller.start()
                if axis:
                    # Reconfigure basic parameters
                    axis.setUnits(Units.mm)
                    time.sleep(0.1)
                    axis.sendCommand("POLI=50") 
                    time.sleep(0.1)
                    axis.sendCommand("ENBL=1")
                    time.sleep(0.1)
                    
                logger.info("Aggressive thermal recovery: Controller reset and reinitialized")
                return True
        except Exception as e:
            logger.error(f"Aggressive thermal recovery failed: {str(e)}")
            return False
    
    return True

# ===== POSITION LIMIT SAFETY ENHANCEMENT =====
# Add this before making any position moves:
def check_position_safety(target_position):
    """Check if a target position is within safe limits."""
    # Hard limits with extra safety margin
    MIN_SAFE_POSITION = -29.0  # 1mm safety margin from -30mm
    MAX_SAFE_POSITION = 29.0   # 1mm safety margin from +30mm
    
    if target_position < MIN_SAFE_POSITION:
        logger.warning(f"Position safety limit would be exceeded: {target_position}mm < {MIN_SAFE_POSITION}mm")
        return False, MIN_SAFE_POSITION
    elif target_position > MAX_SAFE_POSITION:
        logger.warning(f"Position safety limit would be exceeded: {target_position}mm > {MAX_SAFE_POSITION}mm")
        return False, MAX_SAFE_POSITION
    
    return True, target_position

# ===== DEVICE READINESS ERROR HANDLING =====
# Add this function to handle "device reports readiness" errors:
def handle_device_readiness_error(e):
    """Handle 'device reports readiness' errors specially."""
    error_text = str(e).lower()
    
    # Check for the specific error
    if "device reports readiness" in error_text and "returned no data" in error_text:
        logger.warning("Detected device readiness error - applying specialized recovery")
        
        # First, try to flush the serial port aggressively
        flush_serial_port()
        
        # Check if controller is still responsive
        try:
            if axis:
                # Send a simple query that should return quickly
                response = axis.sendCommand("ENBL?")
                logger.debug(f"Controller still responsive, enable status: {response}")
                return True  # Controller seems responsive
        except Exception as inner_e:
            logger.error(f"Controller recovery test failed: {str(inner_e)}")
        
        # More aggressive approach if controller seems unresponsive
        try:
            if controller:
                logger.warning("Controller unresponsive, attempting reset")
                controller.stop()
                time.sleep(1.0)
                
                # Reset USB if possible
                try:
                    subprocess.run(["usbreset", COM_PORT], check=False)
                    time.sleep(1)
                except:
                    pass
                
                # Reinitialize
                controller.start()
                
                # Rebuild axis if needed
                if not axis:
                    axis = controller.addAxis(Stage.XLA_312_3N, "X")
                
                # Restore configuration
                axis.setUnits(Units.mm)
                axis.sendCommand("POLI=50")
                axis.sendCommand("ENBL=1")
                
                logger.info("Controller successfully reset after device readiness error")
                return True
            else:
                logger.error("Cannot recover - controller not initialized")
                return False
        except Exception as reset_e:
            logger.error(f"Controller reset failed: {str(reset_e)}")
            return False
    
    # Not a device readiness error
    return False

# ===== COMMAND PROCESSING ENHANCEMENT =====
# Update your process_command function to include these better error handlers
async def process_command(data):
    """Process incoming commands with enhanced error handling."""
    # ... existing code ...
    
    try:
        # ... existing code for commands ...
        
        # When executing position commands like step or scan,
        # use the timeout wrapper and add more robust error handling:
        
        if command in ["move", "step"]:
            # ... existing parameter validation ...
            
            # Safety check the target position
            final_step = step_value if direction == "right" else -step_value
            with position_lock:
                target_position = current_position + final_step
                safe, adjusted_position = check_position_safety(target_position)
                
                if not safe:
                    # Adjust the step to respect limits
                    logger.warning(f"Step adjusted from {final_step}mm to respect safety limits")
                    final_step = adjusted_position - current_position
            
            # Execute with timeout protection
            try:
                # Enable controller just before the command
                try:
                    axis.sendCommand("ENBL=1")
                except Exception as e:
                    logger.warning(f"Pre-command ENBL=1 failed: {str(e)}")
                
                # Execute step with timeout
                await execute_with_timeout(axis.step, final_step, timeout=10.0)
                
                # Update tracked position and get actual position
                with position_lock:
                    current_position += final_step
                
                epos = await execute_with_timeout(axis.getEPOS, timeout=2.0)
                
                # Update response and log
                response["message"] = f"Stepped {final_step:.6f} mm {'right' if direction == 'right' else 'left'}"
                response["step_executed_mm"] = final_step
                response["epos_mm"] = epos
                logger.info(f"Move executed: {final_step:.6f} mm to position: {epos:.6f} mm")
                last_successful_command_time = time.time()
                
            except Exception as e:
                # Enhanced error handling
                error_str = str(e).lower()
                
                # Check for specific error types
                if "amplifier error" in error_str:
                    amplifier_error_count += 1
                    logger.error(f"Amplifier error detected ({amplifier_error_count} total)")
                    
                    # Try to recover
                    try:
                        axis.sendCommand("ENBL=1")
                        time.sleep(0.1)
                        axis.sendCommand("ENBL=1")  # Double enable for persistence
                    except Exception as recovery_e:
                        logger.error(f"Amplifier error recovery failed: {str(recovery_e)}")
                    
                elif "thermal protection" in error_str:
                    thermal_error_count += 1
                    logger.error(f"Thermal protection error detected ({thermal_error_count} total)")
                    
                    # Use the enhanced thermal recovery
                    await recover_from_thermal_error()
                    
                elif "timeout" in error_str:
                    logger.error(f"Command timeout error: {error_str}")
                    # Already handled by execute_with_timeout
                    
                elif handle_device_readiness_error(e):
                    # This was a device readiness error and recovery was attempted
                    logger.info("Recovery from device readiness error attempted")
                    
                else:
                    # Some other error
                    logger.error(f"Unknown command error: {str(e)}")
                    
                # Re-raise to let the outer handler deal with it
                raise
                
        # Similarly enhance other motor commands

    except Exception as e:
        # ... existing exception handling ...
        pass

# ===== CAMERA BUFFER MANAGEMENT ENHANCEMENT =====
async def manage_camera_buffers():
    """Advanced management of camera buffers to prevent overflow and stalls."""
    global picam2
    
    logger.info("Starting advanced camera buffer management")
    
    while not shutdown_requested:
        try:
            if picam2 and hasattr(picam2, 'started') and picam2.started:
                # Flush buffers
                try:
                    # Capture multiple frames to clear any queue
                    for _ in range(5):
                        _ = picam2.capture_array("main")
                        await asyncio.sleep(0.01)
                        
                    # If available, use more direct buffer control
                    if hasattr(picam2, 'flush_all_ready_buffers'):
                        picam2.flush_all_ready_buffers()
                    
                    logger.debug("Camera buffers flushed")
                except Exception as e:
                    logger.error(f"Camera buffer flush error: {e}")
                
                # Check and report buffer utilization if method available
                try:
                    if hasattr(picam2, 'get_total_buffer_count'):
                        buffer_count = picam2.get_total_buffer_count()
                        logger.debug(f"Camera buffer count: {buffer_count}")
                except:
                    pass
            
            # Sleep 1 second between buffer flushes
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Camera buffer management error: {str(e)}")
            await asyncio.sleep(3)  # Longer sleep on error

# ===== HEALTH MONITORING ENHANCEMENT =====
async def enhanced_health_monitoring():
    """Advanced monitor for system health with auto-recovery."""
    global startup_time, thermal_error_count, amplifier_error_count, serial_error_count
    global last_successful_command_time, last_successful_frame_time
    
    SILENT_THRESHOLD = 60  # Seconds before considering silence problematic
    CPU_WARNING_THRESHOLD = 80  # Percent CPU usage that indicates a problem
    MEMORY_WARNING_THRESHOLD = 80  # Percent memory usage that indicates a problem
    
    logger.info("Starting enhanced health monitoring")
    
    while not shutdown_requested:
        try:
            current_time = time.time()
            uptime = current_time - startup_time
            
            # Calculate silence periods
            command_silence = current_time - last_successful_command_time
            frame_silence = current_time - last_successful_frame_time
            
            # Get system metrics
            cpu_percent = 0
            memory_percent = 0
            
            try:
                # Check CPU and memory if psutil is available
                try:
                    import psutil
                    cpu_percent = psutil.cpu_percent(interval=0.5)
                    memory_percent = psutil.virtual_memory().percent
                except ImportError:
                    # Get CPU from /proc/stat if on Linux
                    if os.path.exists('/proc/stat'):
                        with open('/proc/stat', 'r') as f:
                            cpu_line = f.readline().strip().split()
                            user, nice, system, idle = map(int, cpu_line[1:5])
                            cpu_percent = 100 * (1 - idle / (user + nice + system + idle))
            except:
                pass
            
            # Log health status periodically
            if int(uptime) % 60 == 0:  # Once per minute
                logger.info(
                    f"Health: Uptime={uptime:.1f}s, Silence: cmd={command_silence:.1f}s, frame={frame_silence:.1f}s, "
                    f"CPU={cpu_percent:.1f}%, Memory={memory_percent:.1f}%, "
                    f"Errors: Thermal={thermal_error_count}, Amplifier={amplifier_error_count}, Serial={serial_error_count}"
                )
            
            # Check for issues
            issues_detected = []
            
            if command_silence > SILENT_THRESHOLD:
                issues_detected.append(f"Command silence ({command_silence:.1f}s)")
            
            if frame_silence > SILENT_THRESHOLD:
                issues_detected.append(f"Frame silence ({frame_silence:.1f}s)")
                
            if cpu_percent > CPU_WARNING_THRESHOLD:
                issues_detected.append(f"High CPU usage ({cpu_percent:.1f}%)")
                
            if memory_percent > MEMORY_WARNING_THRESHOLD:
                issues_detected.append(f"High memory usage ({memory_percent:.1f}%)")
            
            # Take action if issues detected
            if issues_detected:
                logger.warning(f"Health issues detected: {', '.join(issues_detected)}")
                
                # For critical issues, attempt recovery
                if command_silence > SILENT_THRESHOLD * 2 or frame_silence > SILENT_THRESHOLD * 2:
                    logger.error("Critical silence detected - attempting system recovery")
                    
                    # Try recovery actions
                    if picam2 and frame_silence > SILENT_THRESHOLD * 2:
                        try:
                            logger.warning("Restarting camera due to frame silence")
                            stop_camera()
                            await asyncio.sleep(1)
                            initialize_camera()
                        except Exception as e:
                            logger.error(f"Camera recovery failed: {str(e)}")
                    
                    if controller and command_silence > SILENT_THRESHOLD * 2:
                        try:
                            logger.warning("Restarting controller due to command silence")
                            stop_controller()
                            await asyncio.sleep(1)
                            initialize_xeryon_controller()
                        except Exception as e:
                            logger.error(f"Controller recovery failed: {str(e)}")
            
            # Wait before next health check
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Health monitor error: {str(e)}")
            await asyncio.sleep(10)

# ===== ENHANCED FIRMWARE INTERACTION =====
def get_firmware_version():
    """Get the firmware version to check for support for advanced commands."""
    global axis
    
    if not RUNNING_ON_RPI or not axis:
        return "unknown"
        
    try:
        # Query controller version
        version = axis.sendCommand("VERS?")
        logger.info(f"Controller firmware version: {version}")
        return str(version)
    except Exception as e:
        logger.error(f"Error getting firmware version: {str(e)}")
        return "unknown"

def setup_advanced_controller_params():
    """Setup advanced controller parameters based on firmware version."""
    global axis
    
    if not RUNNING_ON_RPI or not axis:
        return
        
    try:
        # Get firmware version
        version = get_firmware_version()
        
        # Set universal parameters
        try:
            # Set polling rate
            axis.sendCommand("POLI=50")
            time.sleep(0.1)
            
            # Enable controller
            axis.sendCommand("ENBL=1")
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error setting basic parameters: {str(e)}")
        
        # Set default speed, acceleration, and deceleration
        try:
            axis.setSpeed(DEFAULT_SPEED)
            time.sleep(0.1)
            set_acce_dece_params(DEFAULT_ACCELERATION, DEFAULT_DECELERATION)
            time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error setting motion parameters: {str(e)}")
            
        # Set additional parameters based on version if available
        # Newer firmware versions have additional stability features
        if "4." in version or "5." in version:  # For version 4.x or 5.x
            try:
                # Enhanced stability mode if available
                axis.sendCommand("ESMO=1")
                time.sleep(0.1)
                
                # Set error recovery mode if available
                axis.sendCommand("ERMO=2")  # Auto-recovery mode
                time.sleep(0.1)
                
                logger.info("Advanced controller parameters set for firmware v4+")
            except Exception as e:
                logger.warning(f"Error setting advanced parameters: {str(e)}")
                
        logger.info("Controller parameters setup complete")
    except Exception as e:
        logger.error(f"Error in controller setup: {str(e)}")

# ===== MAIN CLIENT ENHANCEMENTS =====
# Update the main client function to incorporate these enhancements
async def enhanced_rpi_client():
    """Main client function with advanced robustness features."""
    global shutdown_requested, reconnect_delay, total_connection_failures
    global startup_time
    
    startup_time = time.time()
    logger.info(f"Starting Enhanced RPi Client for {STATION_ID}")
    logger.info(f"Connecting to server: {SERVER_URL}")
    
    # Initialize hardware with retry logic
    if RUNNING_ON_RPI:
        # Hard limit on connection failures before complete restart
        MAX_TOTAL_FAILURES = 50
        
        # Initialize camera with proper retries
        camera_ok = False
        for attempt in range(3):
            logger.info(f"Camera initialization attempt {attempt+1}/3")
            camera_ok = initialize_camera()
            if camera_ok:
                break
            await asyncio.sleep(2)
        
        # Initialize controller with proper retries  
        controller_ok = False
        for attempt in range(3):
            logger.info(f"Controller initialization attempt {attempt+1}/3")
            controller_ok = initialize_xeryon_controller()
            if controller_ok:
                # Set up advanced controller parameters
                setup_advanced_controller_params()
                break
            await asyncio.sleep(2)
    
    # Start background tasks
    # Start enhanced health monitoring
    health_monitor_task = asyncio.create_task(enhanced_health_monitoring())
    
    # Start advanced camera buffer management
    camera_buffer_task = asyncio.create_task(manage_camera_buffers())
    
    # Start command processor
    cmd_processor_task = asyncio.create_task(command_processor())
    
    # Main connection loop with exponential backoff and jitter
    while not shutdown_requested:
        try:
            logger.info(f"Connecting to {SERVER_URL} (attempt {total_connection_failures + 1})...")
            
            # Check if we've reached the hard limit for failures
            if total_connection_failures > MAX_TOTAL_FAILURES:
                logger.critical(f"Reached maximum connection failures ({MAX_TOTAL_FAILURES}), restarting application")
                # Request system restart if available
                try:
                    subprocess.run(["sudo", "reboot"], check=False)
                except:
                    pass
                # In case reboot fails or isn't available, exit process
                shutdown_requested = True
                break
            
            # Connect with optimized settings
            websocket = await websockets.connect(
                SERVER_URL,
                ping_interval=None,  # We'll do our own ping/pong
                close_timeout=2,  # Faster timeout for responsive reconnection
                max_size=10_000_000,  # Allow large messages for camera frames
                compression=None  # Disable compression for speed - we compress JPEGs ourselves
            )
            
            logger.info("WebSocket connection established")
            
            # ... rest of the connection handling ...
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            
            # Implement advanced exponential backoff with jitter
            total_connection_failures += 1
            
            # Calculate backoff time based on failures but with a max
            reconnect_delay = min(MAX_RECONNECT_DELAY, 
                               RECONNECT_BASE_DELAY * (1.5 ** min(total_connection_failures, 10)))
            
            # Add jitter (±30%) to prevent thundering herd problem
            jitter_factor = random.uniform(0.7, 1.3)
            actual_delay = reconnect_delay * jitter_factor
            
            logger.info(f"Retrying connection in {actual_delay:.1f}s (attempt {total_connection_failures})...")
            await asyncio.sleep(actual_delay)
            
            # Perform incremental hardware resets based on failure count
            if total_connection_failures % 3 == 0:
                logger.warning(f"Multiple connection failures ({total_connection_failures}), resetting camera")
                if RUNNING_ON_RPI:
                    stop_camera()
                    await asyncio.sleep(1)
                    initialize_camera()
            
            if total_connection_failures % 5 == 0:
                logger.warning(f"Multiple connection failures ({total_connection_failures}), resetting controller")
                if RUNNING_ON_RPI:
                    stop_controller()
                    await asyncio.sleep(1)
                    initialize_xeryon_controller()
                    setup_advanced_controller_params()
            
            # If too many failures and USB issues, try to reset USB completely
            if total_connection_failures % 10 == 0:
                logger.warning(f"Many connection failures ({total_connection_failures}), resetting USB subsystem")
                if RUNNING_ON_RPI:
                    try:
                        # Reset USB more aggressively
                        subprocess.run(["sudo", "rmmod", "ftdi_sio"], check=False)
                        subprocess.run(["sudo", "rmmod", "usbserial"], check=False)
                        await asyncio.sleep(1)
                        subprocess.run(["sudo", "modprobe", "usbserial"], check=False)
                        subprocess.run(["sudo", "modprobe", "ftdi_sio"], check=False)
                        await asyncio.sleep(2)
                    except:
                        pass

# Add the Signal Handling for Graceful Shutdown
def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    loop = asyncio.get_running_loop()
    
    for sig_name in ('SIGINT', 'SIGTERM'):
        try:
            sig = getattr(signal, sig_name)
            loop.add_signal_handler(
                sig, 
                lambda s=sig: asyncio.create_task(shutdown(sig=s))
            )
            logger.info(f"Registered {sig_name} handler")
        except (NotImplementedError, AttributeError, ValueError) as e:
            logger.warning(f"Could not set up {sig_name} handler: {e}")

async def shutdown(sig=None):
    """Perform a clean, graceful shutdown."""
    global shutdown_requested
    
    if shutdown_requested:
        return
        
    reason = f"signal {sig}" if sig else "internal request"
    logger.info(f"Shutdown initiated by {reason}")
    shutdown_requested = True
    
    # Cancel any running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    # Clean up hardware
    if RUNNING_ON_RPI:
        logger.info("Stopping camera and controller")
        stop_camera()
        stop_controller()
    
    # Give tasks time to clean up
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    
    # Final cleanup
    gc.collect()
    logger.info("Shutdown complete - exiting gracefully")

# Update the main entry point
if __name__ == "__main__":
    try:
        # Set process name for better monitoring
        try:
            import setproctitle
            setproctitle.setproctitle("xeryon_rpi_client")
        except ImportError:
            pass
            
        # Run the main client
        asyncio.run(enhanced_rpi_client())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {str(e)}")
        # Emergency hardware cleanup
        if RUNNING_ON_RPI:
            try:
                if 'picam2' in globals() and picam2:
                    stop_camera()
                if 'controller' in globals() and controller:
                    stop_controller()
            except:
                pass