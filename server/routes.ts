import type { Express } from "express";
import { Server } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import type { WebSocketMessage } from "@shared/schema";
import path from "path";
import fs from "fs/promises";
import express from "express";
import multer from "multer";

const uploadsPath = path.join(process.cwd(), "public", "uploads");

const upload = multer({
  dest: uploadsPath,
  limits: { fileSize: 5 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const allowedTypes = ["image/jpeg", "image/png", "image/webp"];
    if (allowedTypes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error("Invalid file type"));
    }
  },
});

const rpiConnections = new Map<string, WebSocket>();
const uiConnections = new Set<WebSocket>();

function isAdmin(req: Express.Request) {
  return req.isAuthenticated() && req.user?.isAdmin;
}

export async function registerRoutes(app: Express): Promise<Server> {
  const httpServer = new Server(app);

  const wss = new WebSocketServer({ noServer: true });

  httpServer.on("upgrade", (req, socket, head) => {
    const urlPath = req.url || "";
    console.log(`[WebSocket] Upgrade request: ${urlPath}`);

    if (urlPath === "/") {
      wss.handleUpgrade(req, socket, head, (ws) => {
        wss.emit("connection", ws, req);
      });
    } else {
      console.log(`[WebSocket] Rejected unknown path: ${urlPath}`);
      socket.write("HTTP/1.1 404 Not Found\r\n\r\n");
      socket.destroy();
    }
  });

  wss.on("connection", (ws, req) => {
    console.log("[WebSocket] New connection established");

    ws.on("message", (data) => {
      try {
        const response = JSON.parse(data.toString());
        console.log("[WebSocket] Received message:", response);

        if (response.type === "register" && response.rpi_id) {
          const rpiId = response.rpi_id;
          console.log(`[WebSocket] RPi ${rpiId} registered with status: ${response.status}`);
          rpiConnections.set(rpiId, ws);
          uiConnections.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(JSON.stringify({
                type: "rpi_connected",
                rpiId,
                status: response.status,
                message: response.message,
              }));
            }
          });
        } else if (response.type === "command_sent") {
          const rpiWs = rpiConnections.get(response.rpiId);
          if (rpiWs && rpiWs.readyState === WebSocket.OPEN) {
            rpiWs.send(JSON.stringify(response));
          } else {
            console.log(`[WebSocket] RPi ${response.rpiId} not connected`);
          }
        } else {
          uiConnections.add(ws);
          const message = response as WebSocketMessage;
          const rpiWs = rpiConnections.get(message.rpiId);
          if (rpiWs && rpiWs.readyState === WebSocket.OPEN) {
            const commandMessage = {
              type: "command_sent",
              command: message.command,
              direction: message.direction || "none",
            };
            console.log(`[WebSocket] Sending command to RPi ${message.rpiId}:`, commandMessage);
            rpiWs.send(JSON.stringify(commandMessage));
          }
        }
      } catch (err) {
        console.error(`[WebSocket] Error handling message: ${err}`);
      }
    });

    ws.on("close", () => {
      console.log("[WebSocket] Connection closed");
      uiConnections.delete(ws);
      // Use Map.forEach instead of for...of
      rpiConnections.forEach((rpiWs, rpiId) => { // Line 105 fix
        if (rpiWs === ws) {
          rpiConnections.delete(rpiId);
          uiConnections.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(JSON.stringify({ type: "rpi_disconnected", rpiId }));
            }
          });
        }
      });
    });

    ws.on("error", (error) => {
      console.error(`[WebSocket] Error: ${error}`);
    });
  });

  await fs.mkdir(uploadsPath, { recursive: true })
    .catch((err) => console.error("Error creating uploads directory:", err));

  app.use("/uploads", express.static(uploadsPath));

  app.use((req, res, next) => {
    console.log(`Auth status for ${req.path}: isAuthenticated=${req.isAuthenticated()}, isAdmin=${isAdmin(req)}`);
    next();
  });

  app.get("/api/stations", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations");
      return res.sendStatus(401);
    }
    const stations = await storage.getStations();
    res.json(stations);
  });

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
    } catch (error: any) {
      console.error("Error creating station:", error);
      res.status(500).json({ message: "Failed to create station" });
    }
  });

  app.patch("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/stations PATCH");
      return res.sendStatus(403);
    }
    const { name } = req.body;
    const stationId = parseInt(req.params.id);

    try {
      const station = await storage.updateStation(stationId, { name });
      res.json(station);
    } catch (error: any) {
      console.error("Error updating station:", error);
      res.status(500).json({ message: "Failed to update station" });
    }
  });

  app.delete("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/stations DELETE");
      return res.sendStatus(403);
    }
    try {
      await storage.deleteStation(parseInt(req.params.id));
      res.sendStatus(200);
    } catch (error: any) {
      console.error("Error deleting station:", error);
      res.status(500).json({ message: "Failed to delete station" });
    }
  });

  app.post("/api/admin/stations/:id/image", upload.single("image"), async (req, res) => {
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
        previewImage: imageUrl,
      });

      res.json({ url: imageUrl });
    } catch (error: any) {
      console.error("Error handling image upload:", error);
      res.status(500).json({ message: "Failed to process image upload" });
    }
  });

  app.post("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations/:id/session POST");
      return res.sendStatus(401);
    }
    try {
      const station = await storage.getStation(parseInt(req.params.id));

      if (!station) {
        return res.status(404).send("Station not found");
      }

      if (station.status === "in_use") {
        return res.status(400).send("Station is in use");
      }

      const updatedStation = await storage.updateStationSession(station.id, req.user?.id || 0);
      res.json(updatedStation);

      setTimeout(async () => {
        try {
          await storage.updateStationSession(station.id, null);
          wss.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
              client.send(JSON.stringify({ type: "session_ended", stationId: station.id }));
            }
          });
        } catch (error: any) {
          console.error("Error ending session:", error);
        }
      }, 5 * 60 * 1000);
    } catch (error: any) {
      console.error("Error starting session:", error);
      res.status(500).json({ message: "Failed to start session" });
    }
  });

  app.delete("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/stations/:id/session DELETE");
      return res.sendStatus(401);
    }
    try {
      const station = await storage.getStation(parseInt(req.params.id));

      if (!station) {
        return res.status(404).send("Station not found");
      }

      if (station.currentUserId !== req.user?.id) {
        return res.status(403).send("Not your session");
      }

      const updatedStation = await storage.updateStationSession(station.id, null);
      res.json(updatedStation);
    } catch (error: any) {
      console.error("Error ending session:", error);
      res.status(500).json({ message: "Failed to end session" });
    }
  });

  app.get("/api/stations/:id/camera", (req, res) => {
    res.status(200).send("Camera feed placeholder");
  });

  return httpServer;
}