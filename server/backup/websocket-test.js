
// Simple standalone WebSocket test that works with Replit's HTTP handling
import express from 'express';
import { WebSocketServer } from 'ws';
import http from 'http';

// Create HTTP server
const app = express();
app.get('/', (req, res) => {
  res.send('WebSocket test server is running. Connect to /websocket-test');
});

// Create WebSocket server
const server = http.createServer(app);

// Create WebSocket server using the HTTP server
const wss = new WebSocketServer({ 
  server,
  path: '/websocket-test' // Specific path for WebSocket connections
});

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

// Use a different port than your main app and ensure it doesn't conflict
const PORT = process.env.REPL_SLUG ? 3334 : 3333; // Use 3334 in production, 3333 locally
server.listen(PORT, '0.0.0.0', () => {
  console.log(`WebSocket test server running on port ${PORT}`);
  console.log(`WebSocket URL: ws://${process.env.REPL_SLUG || 'localhost'}:${PORT}/websocket-test`);
  console.log(`HTTP URL: http://${process.env.REPL_SLUG || 'localhost'}:${PORT}`);
});
