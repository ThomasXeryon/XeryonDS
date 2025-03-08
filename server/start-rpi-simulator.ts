
import { startRPiClient } from './rpi-client';

// Get the RPi ID from command line arguments or use a default
const rpiId = process.argv[2] || 'station-1';

console.log(`Starting RPi simulator with ID: ${rpiId}`);
startRPiClient(rpiId, 'ws://localhost:5000');

// Keep the process running
process.on('SIGINT', () => {
  console.log('Shutting down RPi simulator');
  process.exit(0);
});
