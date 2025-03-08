
// Simple standalone WebSocket test server
const { WebSocketServer } = require('ws');
const http = require('http');

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('WebSocket test server running');
});

// Create a very simple WebSocket server
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  console.log('Client connected!');
  
  // Send a welcome message
  ws.send(JSON.stringify({ 
    message: 'Hello from WebSocket server!',
    timestamp: new Date().toISOString()
  }));
  
  // Handle messages
  ws.on('message', (message) => {
    console.log('Received:', message.toString());
    
    // Echo back
    ws.send(JSON.stringify({ 
      type: 'echo',
      message: message.toString(),
      timestamp: new Date().toISOString()
    }));
  });
  
  ws.on('close', () => {
    console.log('Client disconnected');
  });
  
  ws.on('error', (error) => {
    console.error('WebSocket error:', error);
  });
});

// Start server on a different port to avoid conflicts
const PORT = 3333;
server.listen(PORT, '0.0.0.0', () => {
  console.log(`WebSocket test server running on port ${PORT}`);
  console.log(`WebSocket URL: ws://${process.env.REPL_SLUG}.${process.env.REPL_OWNER}.repl.co:${PORT}`);
  console.log(`HTTP URL: https://${process.env.REPL_SLUG}.${process.env.REPL_OWNER}.repl.co:${PORT}`);
});
