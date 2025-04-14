"""
A simple helper module to ensure the new-demo-program.py can be imported properly
by the combined-rpi-client.py script.

This is needed because Python modules have to be in the Python path and the
directory structure doesn't match the import statement.
"""
import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def install_new_demo():
    """Makes the new-demo-program.py importable"""
    try:
        # Get the current directory (where this file is)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create a symlink from new_demo_program.py to new-demo-program.py
        # This will allow the import statement to work
        if not os.path.exists(os.path.join(current_dir, 'new_demo_program.py')):
            os.symlink(
                os.path.join(current_dir, 'new-demo-program.py'),
                os.path.join(current_dir, 'new_demo_program.py')
            )
            logger.info("Created symlink for new_demo_program.py")
        
        # Add the current directory to the Python path if it's not there
        if current_dir not in sys.path:
            sys.path.append(current_dir)
            logger.info(f"Added {current_dir} to Python path")
        
        return True
    except Exception as e:
        logger.error(f"Error installing new demo program: {str(e)}")
        return False