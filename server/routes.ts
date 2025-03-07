import type { Express } from "express";
import { createServer, type Server } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import type { WebSocketMessage, RPiResponse } from "@shared/schema";
import { parse as parseCookie } from "cookie";
import path from "path";
import fs from "fs/promises";
import express from "express";
import multer from "multer";

// Map to store RPi WebSocket connections
const rpiConnections = new Map<string, WebSocket>();

function isAdmin(req: Express.Request) {
  return req.isAuthenticated() && req.user?.isAdmin;
}

export async function registerRoutes(app: Express): Promise<Server> {
  setupAuth(app);

  const httpServer = createServer(app);

  // WebSocket server for web UI clients
  const wssUI = new WebSocketServer({ 
    server: httpServer, 
    path: "/ws"
  });

  // WebSocket server for RPi clients
  const wssRPi = new WebSocketServer({ 
    server: httpServer, 
    path: "/rpi"
  });

  // Handle RPi connections
  wssRPi.on("connection", (ws, req) => {
    // Extract RPi ID from URL path
    const rpiId = req.url?.split("/").pop();
    if (!rpiId) {
      ws.close(1008, "RPi ID required");
      return;
    }

    console.log(`RPi connected: ${rpiId}`);
    rpiConnections.set(rpiId, ws);

    ws.on("message", (data) => {
      try {
        const message = JSON.parse(data.toString()) as RPiResponse;
        // Broadcast RPi response to all connected UI clients
        wssUI.clients.forEach((client) => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
              type: "rpi_response",
              rpiId,
              ...message
            }));
          }
        });
      } catch (err) {
        console.error(`Error handling RPi message: ${err}`);
      }
    });

    ws.on("close", () => {
      console.log(`RPi disconnected: ${rpiId}`);
      rpiConnections.delete(rpiId);
    });

    ws.on("error", (error) => {
      console.error(`RPi WebSocket error: ${error}`);
    });
  });

  // Handle web UI client connections
  wssUI.on("connection", (ws, req) => {
    let authenticated = false;

    // Authenticate WebSocket connection using session cookie
    if (req.headers.cookie) {
      const cookies = parseCookie(req.headers.cookie);
      const sessionId = cookies["session_id"];
      if (sessionId) {
        authenticated = true;
      }
    }

    if (!authenticated) {
      ws.close(1008, "Authentication required");
      return;
    }

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        const rpiWs = rpiConnections.get(message.rpiId);

        if (!rpiWs || rpiWs.readyState !== WebSocket.OPEN) {
          ws.send(JSON.stringify({ 
            type: "error", 
            message: `RPi ${message.rpiId} not connected` 
          }));
          return;
        }

        // Forward command to specific RPi
        rpiWs.send(JSON.stringify({
          type: message.type,
          command: message.command,
          direction: message.direction
        }));

        // Echo back confirmation
        ws.send(JSON.stringify({ 
          type: "command_sent", 
          rpiId: message.rpiId,
          ...message 
        }));
      } catch (err) {
        console.error("Failed to parse message:", err);
        ws.send(JSON.stringify({ 
          type: "error", 
          message: "Invalid message format" 
        }));
      }
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
    });

    // Send initial connection success message with list of connected RPis
    ws.send(JSON.stringify({ 
      type: "connected",
      connectedRPis: Array.from(rpiConnections.keys())
    }));
  });

  // Serve uploaded files statically
  const uploadsPath = path.join(process.cwd(), 'public', 'uploads');
  // Ensure uploads directory exists
  await fs.mkdir(uploadsPath, { recursive: true })
    .catch(err => console.error('Error creating uploads directory:', err));
  app.use('/uploads', express.static(uploadsPath));

  app.get("/api/stations", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const stations = await storage.getStations();
    res.json(stations);
  });

  // Admin routes
  app.get("/api/admin/users", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const users = await storage.getAllUsers();
    res.json(users);
  });

  app.get("/api/admin/session-logs", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const logs = await storage.getSessionLogs();
    res.json(logs);
  });

  app.patch("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const { name, ipAddress, port, secretKey } = req.body;
    const stationId = parseInt(req.params.id);

    try {
      const station = await storage.updateStation(stationId, {
        name,
        ipAddress,
        port,
        secretKey
      });
      res.json(station);
    } catch (error) {
      console.error("Error updating station:", error);
      res.status(500).json({ message: "Failed to update station" });
    }
  });

  // Feedback routes
  app.post("/api/feedback", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const { type, message } = req.body;

    console.log("Received feedback:", { type, message, userId: req.user.id });

    if (!type || !message) {
      return res.status(400).json({ message: "Type and message are required" });
    }

    try {
      const feedback = await storage.createFeedback(req.user.id, { type, message });
      console.log("Created feedback:", feedback);
      res.json(feedback);
    } catch (error) {
      console.error("Error creating feedback:", error);
      res.status(500).json({ message: "Failed to create feedback" });
    }
  });

  app.get("/api/admin/feedback", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    try {
      const feedback = await storage.getFeedback();
      console.log("Retrieved feedback:", feedback);
      res.json(feedback);
    } catch (error) {
      console.error("Error getting feedback:", error);
      res.status(500).json({ message: "Failed to get feedback" });
    }
  });

  // Settings routes
  app.get("/api/admin/settings", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    try {
      const settings = await storage.getSettings();
      res.json(settings);
    } catch (error) {
      console.error("Error getting settings:", error);
      res.status(500).json({ message: "Failed to get settings" });
    }
  });

  app.post("/api/admin/settings", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const { rpiHost, rpiPort, rpiUsername, rpiPassword } = req.body;

    try {
      const settings = await storage.updateSettings({
        rpiHost,
        rpiPort,
        rpiUsername,
        rpiPassword
      });
      res.json(settings);
    } catch (error) {
      console.error("Error updating settings:", error);
      res.status(500).json({ message: "Failed to update settings" });
    }
  });

  // Other admin routes
  app.post("/api/admin/stations", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const { name, ipAddress, port, secretKey } = req.body;
    if (!name) return res.status(400).json({ message: "Name is required" });

    try {
      const station = await storage.createStation(name);
      // Update the station with connection parameters right after creation
      const updatedStation = await storage.updateStation(station.id, {
        name,
        ipAddress,
        port,
        secretKey
      });
      res.status(201).json(updatedStation);
    } catch (error) {
      console.error("Error creating station:", error);
      res.status(500).json({ message: "Failed to create station" });
    }
  });

  app.delete("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    await storage.deleteStation(parseInt(req.params.id));
    res.sendStatus(200);
  });

  app.post("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const station = await storage.getStation(parseInt(req.params.id));

    if (!station) {
      return res.status(404).send("Station not found");
    }

    if (station.status === "in_use") {
      return res.status(400).send("Station is in use");
    }

    const updatedStation = await storage.updateStationSession(station.id, req.user.id);
    res.json(updatedStation);

    // End session after 5 minutes
    setTimeout(async () => {
      await storage.updateStationSession(station.id, null);
      wssUI.clients.forEach((client) => { 
        if (client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({ type: "session_ended", stationId: station.id }));
        }
      });
    }, 5 * 60 * 1000);
  });

  app.delete("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const station = await storage.getStation(parseInt(req.params.id));

    if (!station) {
      return res.status(404).send("Station not found");
    }

    if (station.currentUserId !== req.user.id) {
      return res.status(403).send("Not your session");
    }

    const updatedStation = await storage.updateStationSession(station.id, null);
    res.json(updatedStation);
  });

  // Configure multer for image uploads
  const upload = multer({
    dest: uploadsPath,
    limits: {
      fileSize: 5 * 1024 * 1024, // 5MB limit
    },
    fileFilter: (_req, file, cb) => {
      const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
      if (allowedTypes.includes(file.mimetype)) {
        cb(null, true);
      } else {
        cb(new Error('Invalid file type'));
      }
    }
  });

  // Add image upload endpoint
  app.post("/api/admin/stations/:id/image",
    upload.single('image'),
    async (req, res) => {
      if (!isAdmin(req)) return res.sendStatus(403);
      if (!req.file) return res.status(400).json({ message: "No file uploaded" });

      const stationId = parseInt(req.params.id);
      const staticPath = path.join(process.cwd(), 'public', 'uploads');

      try {
        // Move file to public directory
        const filename = `station-${stationId}-${Date.now()}${path.extname(req.file.originalname)}`;
        await fs.rename(req.file.path, path.join(staticPath, filename));

        // Update station with image URL
        const imageUrl = `/uploads/${filename}`;
        await storage.updateStation(stationId, {
          name: req.body.name || '',
          ipAddress: req.body.ipAddress || '',
          port: req.body.port || '',
          secretKey: req.body.secretKey || '',
          previewImage: imageUrl
        });

        res.json({ url: imageUrl });
      } catch (error) {
        console.error("Error handling image upload:", error);
        res.status(500).json({ message: "Failed to process image upload" });
      }
    }
  );

  return httpServer;
}