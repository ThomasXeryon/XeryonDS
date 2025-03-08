import type { Express } from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
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

export async function registerRoutes(app: Express) {
  setupAuth(app);
  const stations = await storage.getStations();
  console.log("=== DEMO STATION IDs ===");
  stations.forEach(station => {
    console.log(`Station ID: ${station.id}, Name: ${station.name}, RPi ID: ${station.rpiId}`);
  });
  console.log("=======================");

  const httpServer = createServer(app);

  // Create a single WebSocket server with minimal settings
  const wss = new WebSocketServer({ 
    server: httpServer,
    perMessageDeflate: false // Disable compression
  });

  console.log("WebSocket server created");

  wss.on("connection", (ws, req) => {
    console.log("New WebSocket connection from:", req.socket.remoteAddress);

    ws.on("message", (data) => {
      try {
        // Forward message to all other clients except sender
        wss.clients.forEach(client => {
          if (client !== ws && client.readyState === WebSocket.OPEN) {
            client.send(data.toString());
          }
        });
      } catch (err) {
        console.error("WebSocket message error:", err);
      }
    });

    ws.on("close", () => {
      console.log("Client disconnected");
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
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

    setTimeout(async () => {
      await storage.updateStationSession(station.id, null);
      wss.clients.forEach((client) => { // Updated to use the single wss
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

  function isAdmin(req: Express.Request) {
    return req.isAuthenticated() && req.user?.isAdmin;
  }

  return httpServer;
}