
import { startRPiClient } from './rpi-client';

// Get the RPi ID from command line arguments or use a default
const rpiId = process.argv[2] || 'RPI1';

console.log(`Starting RPi simulator with ID: ${rpiId}`);
const serverUrl = 'ws://localhost:5000/ws';
const client = startRPiClient(rpiId, serverUrl);

// Keep the process running
process.on('SIGINT', () => {
  console.log('Shutting down RPi simulator');
  client.close();
  process.exit(0);
});

// Send simulated data periodically
setInterval(() => {
  client.sendData({
    type: 'telemetry',
    rpiId: rpiId,
    timestamp: Date.now(),
    data: {
      temperature: 25 + Math.random() * 10,
      humidity: 50 + Math.random() * 20,
      status: 'running'
    }
  });
}, 10000);
