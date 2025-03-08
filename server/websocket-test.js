
// Simple WebSocket server test for Replit
const WebSocket = require('ws');
const http = require('http');

// Create simple HTTP server
const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('WebSocket server is running');
});

// Create WebSocket server
const wss = new WebSocket.Server({ server });

// Track connected clients
let clientCount = 0;

// Handle connections
wss.on('connection', (ws, req) => {
  clientCount++;
  const clientId = clientCount;
  console.log(`Client ${clientId} connected from ${req.socket.remoteAddress}`);
  
  // Send welcome message
  ws.send(JSON.stringify({
    type: 'welcome',
    message: `Welcome client ${clientId}!`,
    timestamp: new Date().toISOString()
  }));
  
  // Handle messages
  ws.on('message', (message) => {
    console.log(`Received from client ${clientId}: ${message}`);
    
    // Echo back
    ws.send(JSON.stringify({
      type: 'echo',
      message: message.toString(),
      timestamp: new Date().toISOString()
    }));
  });
  
  // Handle disconnection
  ws.on('close', () => {
    console.log(`Client ${clientId} disconnected`);
  });
  
  // Handle errors
  ws.on('error', (error) => {
    console.error(`Client ${clientId} error:`, error);
  });
});

// Start server
const PORT = 3300;
server.listen(PORT, '0.0.0.0', () => {
  console.log(`WebSocket test server running on port ${PORT}`);
  console.log(`WebSocket URL: ws://${process.env.REPL_SLUG}.${process.env.REPL_OWNER}.repl.co:${PORT}`);
});
