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

// Define uploadsPath at the top level
const uploadsPath = path.join(process.cwd(), 'public', 'uploads');

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
    path: "/rpi",
    verifyClient: (info, callback) => {
      // Get the rpiId from the URL path
      const urlPath = info.req.url || "";
      const pathParts = urlPath.split('/');
      const rpiId = pathParts.pop() || pathParts.pop(); // Handle trailing slash
      
      if (!rpiId) {
        console.log("RPi connection rejected: No RPi ID provided");
        callback(false, 400, "RPi ID required");
        return;
      }
      
      // Store rpiId in request object to access it later
      (info.req as any).rpiId = rpiId;
      callback(true);
    }
  });

  // Handle RPi connections
  wssRPi.on("connection", (ws, req) => {
    // Extract RPi ID from request object (set during verification)
    const rpiId = (req as any).rpiId;

    console.log(`RPi connected: ${rpiId}`);
    rpiConnections.set(rpiId, ws);

    // Notify UI clients about new RPi connection
    wssUI.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({
          type: "rpi_connected",
          rpiId
        }));
      }
    });

    ws.on("message", (data) => {
      try {
        const response = JSON.parse(data.toString());
        console.log(`Message from RPi ${rpiId}:`, response);
        
        // Handle registration message from Python client
        if (response.type === "register") {
          console.log(`RPi ${rpiId} registered successfully with status: ${response.status}`);
          
          // Notify UI clients about the RPi status
          wssUI.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(JSON.stringify({
                type: "rpi_status",
                rpiId,
                status: response.status,
                message: response.message
              }));
            }
          });
          return;
        }

        // Broadcast RPi response to all connected UI clients
        wssUI.clients.forEach((client) => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
              type: "rpi_response",
              rpiId,
              message: response.message,
              status: response.status
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
      // Notify UI clients about disconnected RPi
      wssUI.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({
            type: "rpi_disconnected",
            rpiId
          }));
        }
      });
    });

    ws.on("error", (error) => {
      console.error(`RPi WebSocket error: ${error}`);
    });
  });

  // Handle web UI client connections
  wssUI.on("connection", (ws, req) => {
    // For now, accept all UI connections without authentication
    console.log("UI client connected");

    // Send initial list of connected RPis
    ws.send(JSON.stringify({
      type: "rpi_list",
      rpiIds: Array.from(rpiConnections.keys())
    }));

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        console.log("Received UI message:", message);

        const rpiWs = rpiConnections.get(message.rpiId);

        if (!rpiWs || rpiWs.readyState !== WebSocket.OPEN) {
          console.log(`RPi ${message.rpiId} not connected or not ready`);
          ws.send(JSON.stringify({ 
            type: "error", 
            message: `RPi ${message.rpiId} not connected` 
          }));
          return;
        }

        // Forward command to specific RPi
        const commandMessage = {
          type: message.type,
          command: message.command,
          direction: message.direction
        };

        console.log(`Sending command to RPi ${message.rpiId}:`, commandMessage);
        rpiWs.send(JSON.stringify(commandMessage));

        // Echo back confirmation
        const confirmationMessage = {
          type: "command_sent",
          message: `Command sent to ${message.rpiId}`,
          ...commandMessage
        };

        ws.send(JSON.stringify(confirmationMessage));
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

    ws.on("close", () => {
      console.log("UI client disconnected");
    });
  });

  // Ensure uploads directory exists
  await fs.mkdir(uploadsPath, { recursive: true })
    .catch(err => console.error('Error creating uploads directory:', err));

  // Serve uploaded files statically
  app.use('/uploads', express.static(uploadsPath));

  // Add authentication logging middleware
  app.use((req, res, next) => {
    console.log(`Auth status for ${req.path}: isAuthenticated=${req.isAuthenticated()}, isAdmin=${isAdmin(req)}`);
    next();
  });

  // Station routes
  app.get("/api/stations", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations");
      return res.sendStatus(401);
    }
    const stations = await storage.getStations();
    res.json(stations);
  });

  // Admin routes
  app.post("/api/admin/stations", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/stations POST");
      return res.sendStatus(403);
    }
    const { name, rpiId } = req.body;

    if (!name || !rpiId) {
      return res.status(400).json({ message: "Name and RPi ID are required" });
    }

    try {
      const station = await storage.createStation(name, rpiId);
      res.status(201).json(station);
    } catch (error) {
      console.error("Error creating station:", error);
      res.status(500).json({ message: "Failed to create station" });
    }
  });

  app.patch("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/stations PATCH");
      return res.sendStatus(403);
    }
    const { name, rpiId } = req.body;
    const stationId = parseInt(req.params.id);

    try {
      const station = await storage.updateStation(stationId, { name });
      res.json(station);
    } catch (error) {
      console.error("Error updating station:", error);
      res.status(500).json({ message: "Failed to update station" });
    }
  });

  app.delete("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/stations DELETE");
      return res.sendStatus(403);
    }
    await storage.deleteStation(parseInt(req.params.id));
    res.sendStatus(200);
  });

  // Image upload endpoint
  app.post("/api/admin/stations/:id/image",
    upload.single('image'),
    async (req, res) => {
      if (!isAdmin(req)) {
        console.log("Unauthorized access to /api/admin/stations/:id/image POST");
        return res.sendStatus(403);
      }
      if (!req.file) return res.status(400).json({ message: "No file uploaded" });

      const stationId = parseInt(req.params.id);

      try {
        const filename = `station-${stationId}-${Date.now()}${path.extname(req.file.originalname)}`;
        await fs.rename(req.file.path, path.join(uploadsPath, filename));

        const imageUrl = `/uploads/${filename}`;
        await storage.updateStation(stationId, {
          name: req.body.name || undefined,
          previewImage: imageUrl
        });

        res.json({ url: imageUrl });
      } catch (error) {
        console.error("Error handling image upload:", error);
        res.status(500).json({ message: "Failed to process image upload" });
      }
    }
  );

  // Session management routes
  app.post("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations/:id/session POST");
      return res.sendStatus(401);
    }
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
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations/:id/session DELETE");
      return res.sendStatus(401);
    }
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

  return httpServer;
}