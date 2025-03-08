import type { Express } from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { storage } from "./storage";
import express from "express";
import path from "path";
import fs from "fs";

// Map to store RPi WebSocket connections
const rpiConnections = new Map<string, WebSocket>();

export async function registerRoutes(app: Express) {
  const httpServer = createServer(app);

  // Create WebSocket server attached to HTTP server
  const wss = new WebSocketServer({
    server: httpServer,
    path: '/ws'
  });

  // Create separate WebSocket server for RPi connections
  const rpiWss = new WebSocketServer({
    server: httpServer,
    path: '/rpi'
  });

  // Handle UI client connections
  wss.on('connection', (ws) => {
    console.log('UI client connected');

    ws.on('close', () => {
      console.log('UI client disconnected');
    });

    ws.on('error', (error) => {
      console.error('UI client error:', error);
    });
  });

  // Handle RPi client connections
  rpiWss.on('connection', (ws, req) => {
    const rpiId = req.url?.split('/')[1];
    if (!rpiId) {
      console.error('No RPi ID provided');
      ws.close();
      return;
    }

    console.log(`RPi ${rpiId} connected`);
    rpiConnections.set(rpiId, ws);

    ws.on("message", (data) => {
      try {
        const message = JSON.parse(data.toString());
        if (message.type === 'camera_frame') {
          // Forward frame to all UI clients
          wss.clients.forEach(client => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(data.toString());
            }
          });
        }
      } catch (err) {
        console.error(`Error processing message:`, err);
      }
    });

    ws.on("close", () => {
      console.log(`RPi ${rpiId} disconnected`);
      rpiConnections.delete(rpiId);
    });

    ws.on("error", (error) => {
      console.error(`RPi ${rpiId} error:`, error);
    });
  });

  // Create uploads directory if it doesn't exist
  const uploadsPath = path.join(process.cwd(), 'public', 'uploads');
  await fs.promises.mkdir(uploadsPath, { recursive: true });

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