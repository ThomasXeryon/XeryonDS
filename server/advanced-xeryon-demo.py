"""
Advanced Demo Sequence for Xeryon Actuator
This script creates an exciting, dynamic demo sequence that showcases 
the full capabilities of the Xeryon actuator with varied movements.
"""

import asyncio
import random
import time
import math
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Demo sequence states
DEMO_RUNNING = False
CURRENT_POSITION = 5.0  # mm

# Acceleration and deceleration ranges
MIN_ACCEL = 5000
MAX_ACCEL = 60000
DEFAULT_ACCEL_DECEL = 32750

# Speed ranges
MIN_SPEED = 10    # mm/s
MAX_SPEED = 800   # mm/s

# Step size ranges
TINY_STEP = 0.025  # mm
SMALL_STEP = 0.1   # mm
MEDIUM_STEP = 0.5  # mm
LARGE_STEP = 1.0   # mm
XLARGE_STEP = 2.5  # mm

# Position limits to prevent crashes
MIN_POSITION = 0.0  # mm
MAX_POSITION = 15.0  # mm
SAFE_MARGIN = 1.0   # mm

# Demo pattern sequences
class DemoSequence:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function

async def send_command(command, **params):
    """Simulates sending a command to the Xeryon actuator"""
    global CURRENT_POSITION
    
    if command == "move":
        direction = params.get("direction", "right")
        step_size = params.get("step_size", 0.1)
        accel = params.get("acceleration", DEFAULT_ACCEL_DECEL)
        decel = params.get("deceleration", DEFAULT_ACCEL_DECEL)
        speed = params.get("speed", 100)
        
        logger.info(f"MOVE {direction} step_size={step_size}mm speed={speed}mm/s accel={accel} decel={decel}")
        
        # Update position based on direction
        if direction == "right":
            CURRENT_POSITION += step_size
        else:
            CURRENT_POSITION -= step_size
            
        # Ensure we don't exceed limits
        CURRENT_POSITION = min(max(CURRENT_POSITION, MIN_POSITION), MAX_POSITION)
        
        # Calculate delay based on step size and speed
        delay = (step_size / speed) * 0.5  # Half the theoretical time for animation effect
        await asyncio.sleep(delay)
        
    elif command == "scan":
        direction = params.get("direction", "right")
        accel = params.get("acceleration", DEFAULT_ACCEL_DECEL)
        decel = params.get("deceleration", DEFAULT_ACCEL_DECEL)
        speed = params.get("speed", 100)
        duration = params.get("duration", 1.0)
        
        logger.info(f"SCAN {direction} speed={speed}mm/s accel={accel} decel={decel} duration={duration}s")
        
        # Update position based on scan direction and duration
        distance = speed * duration
        if direction == "right":
            target_pos = CURRENT_POSITION + distance
            # Check if we'd exceed the limit
            if target_pos > MAX_POSITION:
                distance = MAX_POSITION - CURRENT_POSITION
        else:
            target_pos = CURRENT_POSITION - distance
            # Check if we'd exceed the limit
            if target_pos < MIN_POSITION:
                distance = CURRENT_POSITION - MIN_POSITION
                
        # Update position
        if direction == "right":
            CURRENT_POSITION += distance
        else:
            CURRENT_POSITION -= distance
            
        # Ensure we don't exceed limits
        CURRENT_POSITION = min(max(CURRENT_POSITION, MIN_POSITION), MAX_POSITION)
        
        await asyncio.sleep(duration)
        
    elif command == "stop":
        logger.info("STOP")
        await asyncio.sleep(0.1)
        
    elif command == "set_speed":
        speed = params.get("speed", 100)
        logger.info(f"SET SPEED {speed}mm/s")
        await asyncio.sleep(0.05)
        
    elif command == "set_acceleration":
        accel = params.get("acceleration", DEFAULT_ACCEL_DECEL)
        logger.info(f"SET ACCELERATION {accel}")
        await asyncio.sleep(0.05)
        
    elif command == "set_deceleration":
        decel = params.get("deceleration", DEFAULT_ACCEL_DECEL)
        logger.info(f"SET DECELERATION {decel}")
        await asyncio.sleep(0.05)
        
    elif command == "home":
        logger.info("HOMING")
        # Move to the home position (5.0mm) with default parameters
        original_pos = CURRENT_POSITION
        CURRENT_POSITION = 5.0
        
        # Simulate movement time
        distance = abs(original_pos - CURRENT_POSITION)
        await asyncio.sleep(distance / 100)  # Assume 100mm/s for homing

    return CURRENT_POSITION

def get_safe_params(current_position):
    """Get parameters that ensure the actuator stays within safe limits"""
    # Calculate how much room we have left and right
    room_left = current_position - MIN_POSITION
    room_right = MAX_POSITION - current_position
    
    # Direction biased toward where we have more room
    direction = "right" if room_right > room_left else "left"
    
    # Step size limited by available room (with safety margin)
    max_step = min(room_left, room_right) - SAFE_MARGIN
    max_step = max(max_step, TINY_STEP)  # Ensure at least a tiny step is possible
    
    return {
        "direction": direction,
        "max_step": max_step
    }

async def sequence_precision_showcase():
    """Sequence that showcases precision with tiny steps"""
    logger.info("◆◆◆ STARTING PRECISION SHOWCASE ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Set high acceleration for crisp movements
    accel = random.randint(40000, 60000)
    decel = random.randint(40000, 60000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # Do a series of precisely-controlled tiny steps
    await send_command("set_speed", speed=50)  # Slow speed for precision
    
    # Do 10 tiny steps in alternating directions
    direction = safe_params["direction"]
    for i in range(10):
        step_size = TINY_STEP
        await send_command("move", direction=direction, step_size=step_size, 
                          acceleration=accel, deceleration=decel, speed=50)
        # Alternate direction
        direction = "right" if direction == "left" else "left"
        
    logger.info("◆◆◆ PRECISION SHOWCASE COMPLETE ◆◆◆")

async def sequence_speed_rush():
    """Sequence that demonstrates high speed movement"""
    logger.info("◆◆◆ STARTING SPEED RUSH ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Set medium-high acceleration for quick startups
    accel = random.randint(30000, 50000)
    decel = random.randint(30000, 50000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # Start with medium speed and increase
    speeds = [200, 400, 600, 800]
    direction = safe_params["direction"]
    
    for speed in speeds:
        await send_command("set_speed", speed=speed)
        
        # Calculate safe step size based on available space
        safe_params = get_safe_params(CURRENT_POSITION)
        step_size = min(MEDIUM_STEP, safe_params["max_step"] * 0.5)  # Use 50% of available space
        
        # Move at increasing speeds
        await send_command("move", direction=direction, step_size=step_size,
                          acceleration=accel, deceleration=decel, speed=speed)
        
        # Change direction after each move
        direction = "right" if direction == "left" else "left"
    
    logger.info("◆◆◆ SPEED RUSH COMPLETE ◆◆◆")

async def sequence_scanning_pattern():
    """Sequence that demonstrates scanning in various patterns"""
    logger.info("◆◆◆ STARTING SCANNING PATTERN ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # High acceleration/deceleration for this pattern
    accel = random.randint(40000, 60000)
    decel = random.randint(40000, 60000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # Do scanning patterns (right-left-right) with varying speeds
    scan_speeds = [100, 300, 500]
    
    for speed in scan_speeds:
        await send_command("set_speed", speed=speed)
        
        # Calculate scan durations to stay within limits
        safe_params = get_safe_params(CURRENT_POSITION)
        direction = safe_params["direction"]
        
        # Scan in one direction
        scan_duration = min(1.0, safe_params["max_step"] / speed)
        await send_command("scan", direction=direction, 
                          acceleration=accel, deceleration=decel,
                          speed=speed, duration=scan_duration)
        
        # Update safe params and scan in opposite direction
        safe_params = get_safe_params(CURRENT_POSITION)
        direction = "right" if direction == "left" else "left"
        scan_duration = min(1.5, safe_params["max_step"] / speed)
        await send_command("scan", direction=direction,
                          acceleration=accel, deceleration=decel,
                          speed=speed, duration=scan_duration)
        
        # Brief pause
        await asyncio.sleep(0.1)
    
    logger.info("◆◆◆ SCANNING PATTERN COMPLETE ◆◆◆")

async def sequence_staircase():
    """Sequence that creates a staircase pattern with steps"""
    logger.info("◆◆◆ STARTING STAIRCASE PATTERN ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Medium acceleration/deceleration
    accel = random.randint(20000, 40000)
    decel = random.randint(20000, 40000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # Determine direction for staircase (prefer direction with more room)
    direction = safe_params["direction"]
    step_sizes = [SMALL_STEP, MEDIUM_STEP, LARGE_STEP, MEDIUM_STEP, SMALL_STEP]
    
    # Set a medium speed
    await send_command("set_speed", speed=300)
    
    # Create staircase pattern
    for step_size in step_sizes:
        # Ensure step size is safe
        safe_params = get_safe_params(CURRENT_POSITION)
        safe_step = min(step_size, safe_params["max_step"] * 0.8)
        
        # Take step
        await send_command("move", direction=direction, step_size=safe_step,
                          acceleration=accel, deceleration=decel, speed=300)
        
    # Now return in opposite direction with larger steps
    direction = "right" if direction == "left" else "left"
    safe_params = get_safe_params(CURRENT_POSITION)
    safe_step = min(LARGE_STEP * 2, safe_params["max_step"] * 0.8)
    
    await send_command("move", direction=direction, step_size=safe_step,
                      acceleration=accel, deceleration=decel, speed=400)
    
    logger.info("◆◆◆ STAIRCASE PATTERN COMPLETE ◆◆◆")

async def sequence_acceleration_showcase():
    """Sequence that demonstrates different acceleration/deceleration settings"""
    logger.info("◆◆◆ STARTING ACCELERATION SHOWCASE ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Start direction
    direction = safe_params["direction"]
    
    # Vary acceleration/deceleration while keeping speed constant
    accel_values = [10000, 30000, 60000]
    decel_values = [10000, 30000, 60000]
    
    # Set medium speed
    await send_command("set_speed", speed=300)
    
    # Demonstrate various acceleration patterns
    for accel in accel_values:
        for decel in decel_values:
            await send_command("set_acceleration", acceleration=accel)
            await send_command("set_deceleration", deceleration=decel)
            
            # Calculate safe step size
            safe_params = get_safe_params(CURRENT_POSITION)
            step_size = min(MEDIUM_STEP, safe_params["max_step"] * 0.6)
            
            # Take step with these accel/decel settings
            await send_command("move", direction=direction, step_size=step_size,
                              acceleration=accel, deceleration=decel, speed=300)
            
            # Change direction after each move
            direction = "right" if direction == "left" else "left"
            
            # Small delay between moves for visual effect
            await asyncio.sleep(0.1)
    
    logger.info("◆◆◆ ACCELERATION SHOWCASE COMPLETE ◆◆◆")

async def sequence_rapid_fire():
    """Sequence with rapid small movements to create a visual buzz"""
    logger.info("◆◆◆ STARTING RAPID FIRE SEQUENCE ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Very high acceleration/deceleration
    accel = random.randint(50000, 65000)
    decel = random.randint(50000, 65000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # High speed
    await send_command("set_speed", speed=800)
    
    # Initial direction
    direction = safe_params["direction"]
    
    # Perform 20 rapid tiny steps
    for i in range(20):
        # Ensure we stay within safe limits
        safe_params = get_safe_params(CURRENT_POSITION)
        step_size = min(TINY_STEP, safe_params["max_step"] * 0.5)
        
        await send_command("move", direction=direction, step_size=step_size,
                          acceleration=accel, deceleration=decel, speed=800)
        
        # Alternate direction for each step
        direction = "right" if direction == "left" else "left"
        
        # No explicit delay - let the movement itself be the pacing
    
    logger.info("◆◆◆ RAPID FIRE SEQUENCE COMPLETE ◆◆◆")

async def sequence_dance_party():
    """Sequence with varied movements that create a dance-like pattern"""
    logger.info("◆◆◆ STARTING DANCE PARTY ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # Medium-high acceleration/deceleration
    accel = random.randint(35000, 55000)
    decel = random.randint(35000, 55000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # Dance moves with varying speeds and step sizes
    dance_steps = [
        {"speed": 400, "step_size": SMALL_STEP, "count": 3},
        {"speed": 600, "step_size": MEDIUM_STEP, "count": 1},
        {"speed": 300, "step_size": TINY_STEP, "count": 5},
        {"speed": 700, "step_size": MEDIUM_STEP, "count": 2},
    ]
    
    # Initial direction
    direction = safe_params["direction"]
    
    # Perform the dance sequence
    for dance_step in dance_steps:
        speed = dance_step["speed"]
        step_size = dance_step["step_size"]
        count = dance_step["count"]
        
        await send_command("set_speed", speed=speed)
        
        for i in range(count):
            # Calculate safe step size
            safe_params = get_safe_params(CURRENT_POSITION)
            safe_step = min(step_size, safe_params["max_step"] * 0.7)
            
            # Take step
            await send_command("move", direction=direction, step_size=safe_step,
                              acceleration=accel, deceleration=decel, speed=speed)
            
            # Change direction after each step
            direction = "right" if direction == "left" else "left"
    
    logger.info("◆◆◆ DANCE PARTY COMPLETE ◆◆◆")

async def sequence_grand_finale():
    """Final sequence that combines elements from other sequences"""
    logger.info("◆◆◆ STARTING GRAND FINALE ◆◆◆")
    
    # Get our bearings
    safe_params = get_safe_params(CURRENT_POSITION)
    
    # High acceleration/deceleration for dramatic effect
    accel = random.randint(50000, 65000)
    decel = random.randint(50000, 65000)
    await send_command("set_acceleration", acceleration=accel)
    await send_command("set_deceleration", deceleration=decel)
    
    # First, a sweeping scan to one side
    direction = safe_params["direction"]
    await send_command("set_speed", speed=700)
    
    # Calculate safe scan duration
    scan_duration = min(1.5, safe_params["max_step"] / 700)
    await send_command("scan", direction=direction,
                      acceleration=accel, deceleration=decel,
                      speed=700, duration=scan_duration)
    
    # Then rapid-fire tiny steps back
    opposite_dir = "right" if direction == "left" else "left"
    await send_command("set_speed", speed=600)
    
    for i in range(5):
        safe_params = get_safe_params(CURRENT_POSITION)
        step_size = min(SMALL_STEP, safe_params["max_step"] * 0.6)
        
        await send_command("move", direction=opposite_dir, step_size=step_size,
                          acceleration=accel, deceleration=decel, speed=600)
    
    # Then a dramatic slow, large movement
    await send_command("set_speed", speed=200)
    safe_params = get_safe_params(CURRENT_POSITION)
    step_size = min(LARGE_STEP, safe_params["max_step"] * 0.8)
    
    await send_command("move", direction=direction, step_size=step_size,
                      acceleration=accel, deceleration=decel, speed=200)
    
    # Finally, return home
    await send_command("home")
    
    logger.info("◆◆◆ GRAND FINALE COMPLETE ◆◆◆")

# Create the sequence library
DEMO_SEQUENCES = [
    DemoSequence("precision", "Precision Movement Showcase", sequence_precision_showcase),
    DemoSequence("speed", "High-Speed Movement Demonstration", sequence_speed_rush),
    DemoSequence("scanning", "Scanning Pattern Demonstration", sequence_scanning_pattern),
    DemoSequence("staircase", "Staircase Pattern", sequence_staircase),
    DemoSequence("acceleration", "Acceleration/Deceleration Showcase", sequence_acceleration_showcase),
    DemoSequence("rapid_fire", "Rapid-Fire Movement", sequence_rapid_fire),
    DemoSequence("dance", "Dance Party Pattern", sequence_dance_party),
    DemoSequence("finale", "Grand Finale", sequence_grand_finale)
]

async def run_advanced_demo():
    """Main function to run the advanced demo sequence"""
    global DEMO_RUNNING, CURRENT_POSITION
    
    if DEMO_RUNNING:
        logger.warning("Demo already running, ignoring request")
        return
    
    DEMO_RUNNING = True
    logger.info("▶▶▶ STARTING ADVANCED XERYON DEMO ▶▶▶")
    
    try:
        # First, home the actuator
        await send_command("home")
        
        # Keep track of sequence order for smooth transitions
        sequence_order = [
            "precision",
            "speed",
            "scanning",
            "staircase",
            "acceleration",
            "rapid_fire",
            "dance",
            "finale"
        ]
        
        # Run each sequence in order
        for seq_name in sequence_order:
            # Find the sequence in our library
            sequence = next((s for s in DEMO_SEQUENCES if s.name == seq_name), None)
            
            if sequence:
                # Run the sequence
                await sequence.function()
                
                # Brief pause between sequences for visual effect
                await asyncio.sleep(0.3)
            else:
                logger.warning(f"Sequence {seq_name} not found in library")
        
        logger.info("◀◀◀ ADVANCED XERYON DEMO COMPLETED ◀◀◀")
        
    except Exception as e:
        logger.error(f"Demo error: {str(e)}")
    finally:
        # Make sure we home at the end
        if DEMO_RUNNING:
            await send_command("home")
        DEMO_RUNNING = False

async def stop_demo():
    """Stop the demo if it's running"""
    global DEMO_RUNNING
    
    if DEMO_RUNNING:
        DEMO_RUNNING = False
        logger.info("Demo stopped by request")
        await send_command("stop")
        await send_command("home")

# Main function if running directly
if __name__ == "__main__":
    asyncio.run(run_advanced_demo())