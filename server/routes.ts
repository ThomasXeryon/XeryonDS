import type { Express } from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import path from "path";
import fs from "fs/promises";
import express from "express";
import multer from "multer";

// Map to store RPi WebSocket connections
const rpiConnections = new Map<string, WebSocket>();

// Define uploadsPath at the top level
const uploadsPath = path.join(process.cwd(), 'public', 'uploads');

export async function registerRoutes(app: Express) {
  setupAuth(app);
  const stations = await storage.getStations();
  console.log("=== DEMO STATION IDs ===");
  stations.forEach(station => console.log(`Station ID: ${station.id}, Name: ${station.name}, RPi ID: ${station.rpiId}`));
  console.log("=======================");

  const httpServer = createServer(app);
  const wss = new WebSocketServer({
    noServer: true,
    maxPayload: 100 * 1024 * 1024
  });

  // Handle WebSocket upgrade requests before auth middleware
  httpServer.on('upgrade', (request, socket, head) => {
    const pathname = new URL(request.url!, `http://${request.headers.host}`).pathname;
    console.log('WebSocket upgrade request:', { pathname });

    // Allow /ws and /rpi/* without auth
    if (pathname === '/ws' || pathname.startsWith('/rpi/')) {
      wss.handleUpgrade(request, socket, head, (ws) => {
        if (pathname === '/ws') {
          console.log('UI client connected');
          handleUIConnection(ws);
        } else {
          const rpiId = pathname.split('/')[2];
          console.log(`RPi ${rpiId} connected`);
          handleRPiConnection(ws, rpiId);
        }
      });
    } else {
      socket.destroy();
    }
  });

  function handleRPiConnection(ws: WebSocket, rpiId: string) {
    rpiConnections.set(rpiId, ws);

    ws.on("message", (data) => {
      try {
        const message = JSON.parse(data.toString());
        if (message.type === 'camera_frame') {
          // Simple frame forwarding to all UI clients
          wss.clients.forEach(client => {
            if (client !== ws && client.readyState === WebSocket.OPEN) {
              client.send(data.toString());
            }
          });
        }
      } catch (err) {
        console.error(`RPi message error:`, err);
      }
    });

    ws.on("close", () => {
      console.log(`RPi ${rpiId} disconnected`);
      rpiConnections.delete(rpiId);
    });
  }

  function handleUIConnection(ws: WebSocket) {
    ws.on("message", (data) => {
      try {
        const message = JSON.parse(data.toString());
        console.log('UI client message:', message);
      } catch (err) {
        console.error('UI client message error:', err);
      }
    });

    ws.on("close", () => {
      console.log('UI client disconnected');
    });
  }


  // Configure multer for image uploads
  const upload = multer({
    dest: uploadsPath,
    limits: { fileSize: 5 * 1024 * 1024 }, // 5MB limit
    fileFilter: (_req, file, cb) => {
      const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
      allowedTypes.includes(file.mimetype) ? cb(null, true) : cb(new Error('Invalid file type'));
    }
  });

  // Ensure uploads directory exists
  await fs.mkdir(uploadsPath, { recursive: true });

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
      wss.clients.forEach((client) => {
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