import express, { Router } from "express";
import { Server } from "http";
import { WebSocketServer } from "ws";
import { log } from "./vite";

// Connected RPi clients
const connectedClients = new Map();

export async function registerRoutes(app: express.Express): Promise<Server> {
  const router = Router();
  
  // Basic API routes
  router.get("/api/health", (req, res) => {
    res.json({ status: "ok" });
  });

  // List connected RPi devices
  router.get("/api/devices", (req, res) => {
    const devices = Array.from(connectedClients.entries()).map(([id, client]) => ({
      id,
      status: client.status,
      lastSeen: client.lastSeen
    }));
    res.json({ devices });
  });

  app.use(router);
  
  // Create HTTP server
  const server = new Server(app);
  
  // Create WebSocket server
  const wss = new WebSocketServer({ 
    server,
    path: '/ws'
  });
  
  wss.on('connection', (ws) => {
    let clientId = null;
    
    log('WebSocket client connected', 'ws-server');
    
    ws.on('message', (message) => {
      try {
        const data = JSON.parse(message.toString());
        log(`Received: ${JSON.stringify(data)}`, 'ws-server');
        
        if (data.type === 'register' && data.rpiId) {
          clientId = data.rpiId;
          connectedClients.set(clientId, { 
            ws, 
            status: 'online',
            lastSeen: new Date()
          });
          log(`Registered RPi: ${clientId}`, 'ws-server');
        }
        
        if (data.type === 'heartbeat' && data.rpiId) {
          const client = connectedClients.get(data.rpiId);
          if (client) {
            client.lastSeen = new Date();
            client.status = 'online';
          }
        }
        
        // Broadcast to all clients (for demo purposes)
        wss.clients.forEach(client => {
          if (client !== ws && client.readyState === 1) {
            client.send(JSON.stringify({
              type: 'broadcast',
              from: clientId || 'unknown',
              data: data
            }));
          }
        });
        
      } catch (error) {
        log(`Error processing message: ${error}`, 'ws-server');
      }
    });
    
    ws.on('close', () => {
      log('WebSocket client disconnected', 'ws-server');
      if (clientId) {
        const client = connectedClients.get(clientId);
        if (client) {
          client.status = 'offline';
        }
      }
    });
  });
  
  return server;
}