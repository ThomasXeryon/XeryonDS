
import WebSocket from 'ws';

// Simple RPi client simulator to test WebSocket integration
export function startRPiClient(rpiId: string, serverUrl: string = 'ws://localhost:5000') {
  const ws = new WebSocket(`${serverUrl}/rpi/${rpiId}`);
  
  ws.on('open', () => {
    console.log(`RPi Client ${rpiId} connected to server`);
    
    // Send initial status message
    const initialStatus = {
      status: 'ready',
      message: 'RPi device online and ready to accept commands'
    };
    ws.send(JSON.stringify(initialStatus));
  });
  
  ws.on('message', (data) => {
    try {
      const message = JSON.parse(data.toString());
      console.log(`RPi ${rpiId} received command:`, message);
      
      // Simulate processing and respond with success
      setTimeout(() => {
        const response = {
          status: 'success',
          message: `Executed command: ${message.command || 'unknown'}`
        };
        ws.send(JSON.stringify(response));
      }, 500); // Simulate 500ms processing time
    } catch (err) {
      console.error(`Error processing message on RPi ${rpiId}:`, err);
      ws.send(JSON.stringify({
        status: 'error',
        message: 'Failed to process command'
      }));
    }
  });
  
  ws.on('close', () => {
    console.log(`RPi Client ${rpiId} disconnected`);
    // Try to reconnect after 5 seconds
    setTimeout(() => startRPiClient(rpiId, serverUrl), 5000);
  });
  
  ws.on('error', (error) => {
    console.error(`RPi WebSocket error: ${error}`);
    ws.close();
  });
  
  return ws;
}
