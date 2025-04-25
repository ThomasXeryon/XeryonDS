#!/usr/bin/env python3
"""
Unit Conversion Fix for Xeryon Demo Station Raspberry Pi Client
- Fixes UTF-8 encoding issues with unit conversion
- Handles different unit symbols correctly (mm, µm, nm)
"""

# IMPORTANT: This code fixes the unit conversion in the process_command function
# Replace the relevant section in your RPi client code with this implementation

def process_command(data):
    """Process incoming commands with proper unit handling"""
    # ... [existing code] ...
    
    message_type = data.get("type")
    command = data.get("command", "unknown")
    direction = data.get("direction", "none")
    step_size = data.get("stepSize")
    step_unit = data.get("stepUnit", "mm")  # Default to mm if not specified
    
    # Log everything we received
    logger.debug(
        f"Command received: {command}, direction: {direction}, stepSize: {step_size}, stepUnit: {step_unit}"
    )
    
    # ... [existing code] ...
    
    # FIXED UNIT CONVERSION HANDLING
    # When processing step or move commands:
    if command in ["move", "step"]:
        # Validate parameters
        if direction not in ["right", "left", "up", "down"]:
            raise ValueError(f"Invalid direction: {direction}")
        if step_size is None or not isinstance(step_size, (int, float)) or step_size < 0:
            raise ValueError(f"Invalid stepSize: {step_size}")
        
        # Check for all possible unit representations
        valid_units = ["mm", "µm", "um", "μm", "micrometer", "nm", "nanometer"]
        if step_unit not in valid_units:
            logger.warning(f"Invalid stepUnit: {step_unit}, defaulting to mm")
            step_unit = "mm"

        # Convert to mm (standard unit)
        step_value = float(step_size)
        
        # Handle micrometers (all possible representations)
        if step_unit in ["µm", "um", "μm", "micrometer"]:
            step_value /= 1000.0
            logger.debug(f"Converting from micrometers: {step_size} µm = {step_value} mm")
        # Handle nanometers
        elif step_unit in ["nm", "nanometer"]:
            step_value /= 1_000_000.0
            logger.debug(f"Converting from nanometers: {step_size} nm = {step_value} mm")
        
        # ... [continue with existing code to apply the step_value] ...

# Alternative implementation if modifying the existing code is difficult:
def convert_step_to_mm(step_size, step_unit):
    """Convert a step size from any unit to mm for the Xeryon controller"""
    if step_size is None:
        return 1.0  # Default 1mm
    
    # Convert to float and handle possible string inputs
    try:
        value = float(step_size)
    except (ValueError, TypeError):
        logger.warning(f"Invalid step size value: {step_size}, using default 1.0 mm")
        return 1.0
        
    # Check for all possible unit representations
    if step_unit in ["mm", None, ""]:
        # Already in mm
        return value
    elif step_unit in ["µm", "um", "μm", "micrometer"]:
        # Micrometers to mm (divide by 1000)
        return value / 1000.0
    elif step_unit in ["nm", "nanometer"]:
        # Nanometers to mm (divide by 1,000,000)
        return value / 1_000_000.0
    else:
        # Unknown unit, log warning and use as is (assuming mm)
        logger.warning(f"Unknown unit {step_unit}, treating as mm")
        return value