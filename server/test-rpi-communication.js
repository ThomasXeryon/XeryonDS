
const WebSocket = require('ws');

// The station ID you want to test
const stationId = 8; // Replace with your station ID
const rpiId = 'RPI1'; // Replace with your RPi ID

// Connect to the server's WebSocket endpoint
const wsUrl = 'ws://localhost:5000/ws';
const ws = new WebSocket(wsUrl);

ws.on('open', () => {
  console.log('Connected to WebSocket server');
  
  // Send a test command to the RPi
  const testCommand = {
    type: 'command',
    stationId: stationId,
    rpiId: rpiId,
    command: 'test',
    direction: 'test'
  };
  
  console.log('Sending test command:', testCommand);
  ws.send(JSON.stringify(testCommand));
});

ws.on('message', (data) => {
  try {
    const message = JSON.parse(data.toString());
    console.log('Received response:', message);
    
    // If we get a confirmation, close the connection
    if (message.type === 'command_sent' || message.type === 'error') {
      console.log('Test complete, closing connection');
      ws.close();
    }
  } catch (error) {
    console.error('Error parsing message:', error);
  }
});

ws.on('error', (error) => {
  console.error('WebSocket error:', error);
});

ws.on('close', () => {
  console.log('Connection closed');
  process.exit(0);
});
