import type { Express } from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { storage } from "./storage";
import express from "express";
import path from "path";
import fs from "fs/promises";
import { URL } from 'url';

// Map to store RPi WebSocket connections
const rpiConnections = new Map<string, WebSocket>();

export async function registerRoutes(app: Express) {
  const httpServer = createServer(app);

  // Create WebSocket server with manual upgrade handling
  const wss = new WebSocketServer({ 
    noServer: true,
    perMessageDeflate: false
  });

  // Handle upgrade requests
  httpServer.on('upgrade', (request, socket, head) => {
    try {
      const pathname = new URL(request.url!, `http://${request.headers.host}`).pathname;
      console.log('WebSocket upgrade request for:', pathname);

      if (pathname === '/ws' || pathname.startsWith('/rpi/')) {
        wss.handleUpgrade(request, socket, head, (ws) => {
          wss.emit('connection', ws, request);
        });
      } else {
        // Let other upgrade requests (like Vite HMR) pass through
        socket.destroy();
      }
    } catch (err) {
      console.error('WebSocket upgrade error:', err);
      socket.destroy();
    }
  });

  // Handle WebSocket connections
  wss.on('connection', (ws, request) => {
    const pathname = new URL(request.url!, `http://${request.headers.host}`).pathname;

    // RPi client connection
    if (pathname.startsWith('/rpi/')) {
      const rpiId = pathname.split('/')[2];
      if (!rpiId) {
        console.error('No RPi ID provided');
        ws.close();
        return;
      }

      console.log(`RPi ${rpiId} connected`);
      rpiConnections.set(rpiId, ws);

      ws.on('message', (data) => {
        try {
          const message = JSON.parse(data.toString());
          if (message.type === 'camera_frame') {
            // Forward frame to UI clients
            wss.clients.forEach(client => {
              if (client !== ws && client.readyState === WebSocket.OPEN) {
                client.send(data.toString());
              }
            });
          }
        } catch (err) {
          console.error('Error processing message:', err);
        }
      });

      ws.on('close', () => {
        console.log(`RPi ${rpiId} disconnected`);
        rpiConnections.delete(rpiId);
      });

      ws.on('error', (error) => {
        console.error(`RPi ${rpiId} error:`, error);
      });
    }
    // UI client connection
    else if (pathname === '/ws') {
      console.log('UI client connected');

      ws.on('close', () => {
        console.log('UI client disconnected');
      });

      ws.on('error', (error) => {
        console.error('UI client error:', error);
      });
    }
  });

  // Create uploads directory
  const uploadsPath = path.join(process.cwd(), 'public', 'uploads');
  await fs.mkdir(uploadsPath, { recursive: true });

  // Serve static files
  app.use('/uploads', express.static(uploadsPath));

  // Basic station routes
  app.get("/api/stations", async (_req, res) => {
    try {
      const stations = await storage.getStations();
      res.json(stations);
    } catch (error) {
      console.error("Error fetching stations:", error);
      res.status(500).json({ message: "Failed to fetch stations" });
    }
  });

  // Simple session management
  app.post("/api/stations/:id/session", async (req, res) => {
    try {
      const station = await storage.getStation(parseInt(req.params.id));
      if (!station) {
        return res.status(404).json({ message: "Station not found" });
      }
      const updatedStation = await storage.updateStationSession(station.id, 1);
      res.json(updatedStation);
    } catch (error) {
      console.error("Error updating session:", error);
      res.status(500).json({ message: "Failed to update session" });
    }
  });

  app.delete("/api/stations/:id/session", async (req, res) => {
    try {
      const station = await storage.getStation(parseInt(req.params.id));
      if (!station) {
        return res.status(404).json({ message: "Station not found" });
      }
      const updatedStation = await storage.updateStationSession(station.id, null);
      res.json(updatedStation);
    } catch (error) {
      console.error("Error ending session:", error);
      res.status(500).json({ message: "Failed to end session" });
    }
  });

  return httpServer;
}