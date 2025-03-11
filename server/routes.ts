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
import { URL } from "url";

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

// Map to store UI client connections
const uiConnections = new Map<string, WebSocket>();

export async function registerRoutes(app: Express): Promise<Server> {
  setupAuth(app);

  // Get all demo station IDs and log them to the console
  const stations = await storage.getStations();
  console.log("=== DEMO STATION IDs ===");
  stations.forEach(station => {
    console.log(`Station ID: ${station.id}, Name: ${station.name}, RPi ID: ${station.rpiId}`);
  });
  console.log("=======================");

  const httpServer = createServer(app);

  // Create WebSocket servers but don't attach them to paths yet
  const wssUI = new WebSocketServer({ noServer: true });
  const wssRPi = new WebSocketServer({ noServer: true });

  // Handle WebSocket upgrade requests
  httpServer.on('upgrade', (request, socket, head) => {
    const parsedUrl = new URL(request.url!, `http://${request.headers.host}`);
    const pathname = parsedUrl.pathname;

    console.log(`[WebSocket] Upgrade request received:`, {
      path: pathname,
      headers: request.headers,
      host: request.headers.host
    });

    // Simple path-based routing for WebSockets
    if (pathname.startsWith('/rpi/')) {
      // Extract the RPi ID from the path
      const rpiId = pathname.split('/')[2];

      if (!rpiId) {
        console.error("[WebSocket] No RPi ID provided in connection URL");
        socket.write('HTTP/1.1 400 Bad Request\r\n\r\n');
        socket.destroy();
        return;
      }

      console.log(`[WebSocket] RPi connection request for ID: ${rpiId}`);

      // Store RPi ID in request for later use
      (request as any).rpiId = rpiId;

      // Handle the upgrade for RPi clients
      wssRPi.handleUpgrade(request, socket, head, (ws) => {
        console.log(`[WebSocket] RPi ${rpiId} upgrade successful`);
        wssRPi.emit('connection', ws, request);
      });
    } else if (pathname === '/appws') { // Changed from '/ws' to '/appws'
      // Handle the upgrade for UI clients without authentication
      console.log("[WebSocket] UI client connection request");
      wssUI.handleUpgrade(request, socket, head, (ws) => {
        console.log("[WebSocket] UI client upgrade successful");
        wssUI.emit('connection', ws, request);
      });
    } else {
      console.error(`[WebSocket] Invalid WebSocket path: ${pathname}`);
      socket.write('HTTP/1.1 404 Not Found\r\n\r\n');
      socket.destroy();
    }
  });

  // Handle RPi connections
  wssRPi.on("connection", (ws, req) => {
    const rpiId = (req as any).rpiId;
    console.log(`[RPi ${rpiId}] Connected`);

    // Store the connection
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
        console.log(`[RPi ${rpiId}] Message received: ${response.type}`);

        // Handle camera frames from RPi
        if (response.type === "camera_frame") {
          console.log(`[RPi ${rpiId}] Received camera frame, raw data length: ${response.frame?.length || 0} bytes`);

          // Validate frame data
          if (!response.frame) {
            console.warn(`[RPi ${rpiId}] Received camera_frame without frame data`);
            return;
          }

          // Check if it's already a data URL or just base64
          const isDataUrl = response.frame.startsWith('data:');
          console.log(`[RPi ${rpiId}] Frame format: ${isDataUrl ? 'data URL' : 'raw base64'}`);

          let frameToSend = response.frame;
          if (!isDataUrl) {
            try {
              // Verify it's valid base64 before forwarding
              atob(response.frame);
              frameToSend = `data:image/jpeg;base64,${response.frame}`;
            } catch (e) {
              console.error(`[RPi ${rpiId}] Invalid base64 data received:`, e);
              return;
            }
          }

          let forwardCount = 0;
          wssUI.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              console.log(`[RPi ${rpiId}] Forwarding frame to client, size: ${frameToSend.length} bytes`);
              client.send(JSON.stringify({
                type: "camera_frame",
                rpiId,
                frame: frameToSend
              }));
              forwardCount++;
            }
          });

          console.log(`[RPi ${rpiId}] Forwarded camera frame to ${forwardCount} clients`);
        } else {
          // Handle RPi command responses
          wssUI.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(JSON.stringify({
                type: "rpi_response",
                rpiId,
                status: response.status,
                message: response.message
              }));
            }
          });
        }
      } catch (err) {
        console.error(`[RPi ${rpiId}] Error handling message:`, err);
      }
    });

    ws.on("close", () => {
      console.log(`[RPi ${rpiId}] Disconnected`);
      rpiConnections.delete(rpiId);

      // Notify UI clients about RPi disconnection
      wssUI.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({
            type: "rpi_disconnected",
            rpiId
          }));
        }
      });
    });
  });

  // Handle web UI client connections
  wssUI.on("connection", (ws, req) => {
    console.log("[WebSocket] UI client connected");

    // Send initial list of connected RPis
    const connectedRpis = Array.from(rpiConnections.keys());
    console.log("[WebSocket] Connected RPis:", connectedRpis);

    ws.send(JSON.stringify({
      type: "rpi_list",
      rpiIds: connectedRpis
    }));

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        console.log("[WebSocket] Received UI message:", message);

        if (!message.rpiId) {
          console.error("[WebSocket] Message missing rpiId:", message);
          ws.send(JSON.stringify({
            type: "error",
            message: "RPi ID is required"
          }));
          return;
        }

        const rpiWs = rpiConnections.get(String(message.rpiId));

        if (!rpiWs || rpiWs.readyState !== WebSocket.OPEN) {
          console.log(`[WebSocket] RPi ${message.rpiId} not connected or not ready`);
          ws.send(JSON.stringify({
            type: "error",
            message: `RPi ${message.rpiId} not connected`,
            details: {
              connected: !!rpiWs,
              readyState: rpiWs?.readyState
            }
          }));
          return;
        }

        // Forward command to RPi with timestamp
        const commandMessage = {
          type: "command",
          command: message.command || "unknown",
          direction: message.direction || "none",
          timestamp: new Date().toISOString()
        };

        console.log(`[WebSocket] Sending command to RPi ${message.rpiId}:`, commandMessage);
        rpiWs.send(JSON.stringify(commandMessage));

        // Echo back confirmation
        ws.send(JSON.stringify({
          type: "command_sent",
          message: `Command sent to RPi ${message.rpiId}`,
          ...commandMessage
        }));
      } catch (err) {
        console.error("[WebSocket] Failed to parse message:", err);
        ws.send(JSON.stringify({
          type: "error",
          message: "Invalid message format"
        }));
      }
    });

    ws.on("error", (error) => {
      console.error("[WebSocket] Error:", error);
    });

    ws.on("close", () => {
      console.log("[WebSocket] UI client disconnected");
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
      return res.status(403).json({ message: "Unauthorized: Admin access required" });
    }
    
    console.log("Station creation request body:", req.body);
    const { name, rpiId } = req.body;

    if (!name || !rpiId) {
      return res.status(400).json({ message: "Name and RPi ID are required" });
    }

    try {
      // Check if a station with this rpiId already exists
      const stations = await storage.getStations();
      const existingStation = stations.find(s => s.rpiId === rpiId);
      
      if (existingStation) {
        return res.status(409).json({ message: `A station with RPi ID "${rpiId}" already exists` });
      }
      
      const station = await storage.createStation(name, rpiId);
      console.log("Station created successfully:", station);
      res.status(201).json(station);
    } catch (error) {
      console.error("Error creating station:", error);
      const errorMessage = error instanceof Error ? error.message : "Unknown error";
      res.status(500).json({ message: `Failed to create station: ${errorMessage}` });
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
    // No timeout - session stays active until explicitly ended
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

function isAdmin(req: Express.Request) {
  return req.isAuthenticated() && req.user?.isAdmin;
}