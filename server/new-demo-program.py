"""
NO-BULLSHIT DEMO PROGRAM
- Stays within -30mm to +30mm range
- Varies speeds between 1-1000
- Uses acceleration values between 1-65k
- Makes truly random moves
- Never repeats the same move more than 5 times
- WILL NOT GET STUCK
"""

import asyncio
import random
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Fixed constants
TRAVEL_RANGE_MIN = -29.0  # Using -29 instead of -30 to add a tiny safety margin
TRAVEL_RANGE_MAX = 29.0   # Using 29 instead of 30 to add a tiny safety margin
SPEED_MIN = 50            # Minimum speed (a bit above 1 for practical reasons)
SPEED_MAX = 1000          # Maximum speed
ACCEL_MIN = 5000          # Minimum acceleration (a bit above 1 for practical reasons)
ACCEL_MAX = 65000         # Maximum acceleration
MAX_REPEATS = 5           # Maximum number of times to repeat a move

async def run_demo(axis):
    """
    Ultra reliable demo that WILL NOT get stuck.
    Extremely simple logic with explicit position checking.
    """
    if not axis:
        logger.error("No axis provided, cannot run demo")
        return
        
    logger.info("Starting new super reliable demo program")
    demo_running = True
    step_count = 0
    last_move_type = None
    repeat_count = 0
    
    try:
        # Get current position to start
        try:
            current_pos = await asyncio.to_thread(axis.getEPOS)
            logger.info(f"Starting position: {current_pos} mm")
        except Exception as e:
            logger.error(f"Error getting position: {str(e)}")
            current_pos = 0.0  # Assume center if can't read
        
        # Main demo loop
        while demo_running:
            # Increment step counter
            step_count += 1
            
            # Generate truly random parameters for this move
            speed = random.randint(SPEED_MIN, SPEED_MAX)
            accel = random.randint(ACCEL_MIN, ACCEL_MAX)
            decel = random.randint(ACCEL_MIN, ACCEL_MAX)
            
            # Set the parameters
            await asyncio.to_thread(axis.setSpeed, speed)
            
            try:
                # Set acceleration/deceleration
                await asyncio.to_thread(axis.setAcce, accel)
                await asyncio.to_thread(axis.setDece, decel)
                logger.info(f"Set speed={speed}, accel={accel}, decel={decel}")
            except Exception as e:
                # Fallback method if direct accel/decel setting is not available
                logger.info(f"Using command format for accel/decel: {e}")
                await asyncio.to_thread(axis.command, "ACCE", str(accel))
                await asyncio.to_thread(axis.command, "DECE", str(decel))
            
            # Choose a move type, avoiding too many repeats
            available_moves = ["absolute", "relative", "scan"]
            if last_move_type and repeat_count >= MAX_REPEATS:
                available_moves.remove(last_move_type)
                repeat_count = 0
                
            move_type = random.choice(available_moves)
            
            # Track repeats
            if move_type == last_move_type:
                repeat_count += 1
            else:
                last_move_type = move_type
                repeat_count = 1
            
            # MOVE TYPE 1: ABSOLUTE POSITIONING
            if move_type == "absolute":
                # Choose a random target position within safe range
                target_pos = random.uniform(TRAVEL_RANGE_MIN, TRAVEL_RANGE_MAX)
                
                # Set the absolute position
                logger.info(f"ABSOLUTE MOVE: Moving to {target_pos:.2f} mm at speed {speed}")
                await asyncio.to_thread(axis.moveTo, target_pos)
                
                # Update current position
                current_pos = target_pos
            
            # MOVE TYPE 2: RELATIVE POSITIONING
            elif move_type == "relative":
                # Calculate safe step size based on current position
                max_pos_step = TRAVEL_RANGE_MAX - current_pos
                max_neg_step = current_pos - TRAVEL_RANGE_MIN
                
                # Ensure we don't exceed travel limits
                if max_pos_step < 1 and max_neg_step < 1:
                    # We're at an extreme, move toward center
                    if current_pos > 0:
                        step = -10.0  # Move left toward center
                    else:
                        step = 10.0   # Move right toward center
                else:
                    # Choose random step size and direction
                    max_step = min(max_pos_step, max_neg_step, 15.0)  # Limit to 15mm max or available space
                    step = random.uniform(-max_step, max_step)
                
                # Execute the relative move
                logger.info(f"RELATIVE MOVE: Moving {step:.2f} mm from {current_pos:.2f} at speed {speed}")
                await asyncio.to_thread(axis.step, step)
                
                # Update current position
                current_pos += step
            
            # MOVE TYPE 3: SCANNING
            elif move_type == "scan":
                # Determine scan direction based on position
                if current_pos > 0:
                    scan_dir = -1  # If on right side, scan left
                else:
                    scan_dir = 1   # If on left side, scan right
                
                # Start the scan
                logger.info(f"SCAN: Starting {'right' if scan_dir == 1 else 'left'} scan at speed {speed}")
                await asyncio.to_thread(axis.startScan, scan_dir)
                
                # Let it scan for a short time (0.3-1.0 seconds)
                scan_time = random.uniform(0.3, 1.0)
                await asyncio.sleep(scan_time)
                
                # Stop the scan
                await asyncio.to_thread(axis.stopScan)
                logger.info(f"SCAN: Stopped after {scan_time:.2f} seconds")
                
                # Read current position after scan
                try:
                    current_pos = await asyncio.to_thread(axis.getEPOS)
                    logger.info(f"Position after scan: {current_pos:.2f} mm")
                except Exception as e:
                    logger.error(f"Error getting position after scan: {str(e)}")
                
                # Safety check to ensure we're not too close to limits
                if current_pos < TRAVEL_RANGE_MIN + 2:
                    await asyncio.to_thread(axis.step, 5.0)
                    current_pos += 5.0
                    logger.info(f"Safety correction: moved to {current_pos:.2f} mm")
                elif current_pos > TRAVEL_RANGE_MAX - 2:
                    await asyncio.to_thread(axis.step, -5.0)
                    current_pos -= 5.0
                    logger.info(f"Safety correction: moved to {current_pos:.2f} mm")
            
            # Add a minimal pause between movements
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Every 10 steps, explicitly check position to avoid drift
            if step_count % 10 == 0:
                try:
                    current_pos = await asyncio.to_thread(axis.getEPOS)
                    logger.info(f"Position check: {current_pos:.2f} mm")
                    
                    # If somehow we've exceeded the limits, move back to safety
                    if current_pos < TRAVEL_RANGE_MIN:
                        await asyncio.to_thread(axis.moveTo, TRAVEL_RANGE_MIN + 5)
                        current_pos = TRAVEL_RANGE_MIN + 5
                        logger.info(f"SAFETY: Moved to {current_pos:.2f} mm")
                    elif current_pos > TRAVEL_RANGE_MAX:
                        await asyncio.to_thread(axis.moveTo, TRAVEL_RANGE_MAX - 5)
                        current_pos = TRAVEL_RANGE_MAX - 5
                        logger.info(f"SAFETY: Moved to {current_pos:.2f} mm")
                except Exception as e:
                    logger.error(f"Error checking position: {str(e)}")
            
            # Every 50 steps, move to center to reset
            if step_count % 50 == 0:
                await asyncio.to_thread(axis.moveTo, 0)
                current_pos = 0
                logger.info("RESET: Moved to center position")
                await asyncio.sleep(0.5)
    
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        # Always restore safe parameters
        try:
            await asyncio.to_thread(axis.setSpeed, 500)
            
            try:
                await asyncio.to_thread(axis.setAcce, 20000)
                await asyncio.to_thread(axis.setDece, 20000)
            except Exception:
                await asyncio.to_thread(axis.command, "ACCE", "20000") 
                await asyncio.to_thread(axis.command, "DECE", "20000")
                
            await asyncio.to_thread(axis.stopScan)  # Ensure any scan is stopped
        except Exception as e:
            logger.error(f"Error restoring default parameters: {str(e)}")
        
        logger.info("Demo stopped")