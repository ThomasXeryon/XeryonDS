import type { Express } from "express";
import { createServer, type Server } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import type { WebSocketMessage } from "@shared/schema";
import { parse as parseCookie } from "cookie";
import type { Session } from "express-session";

function isAdmin(req: Express.Request) {
  return req.isAuthenticated() && req.user?.isAdmin;
}

export async function registerRoutes(app: Express): Promise<Server> {
  setupAuth(app);

  const httpServer = createServer(app);
  const wss = new WebSocketServer({ server: httpServer, path: "/ws" });

  // Helper function to broadcast queue updates
  const broadcastQueueUpdate = async (stationId: number) => {
    const queueLength = await storage.getQueueLength(stationId);
    const estimatedWaitTime = queueLength * 5; // 5 minutes per session

    wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({
          type: "queue_update",
          stationId,
          queueLength,
          estimatedWaitTime,
        }));
      }
    });
  };

  // Helper function to broadcast session time updates
  const broadcastSessionTimeUpdate = (stationId: number, remainingTime: number) => {
    wss.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(JSON.stringify({
          type: "session_time_update",
          stationId,
          remainingTime,
        }));
      }
    });
  };

  // Station routes
  app.get("/api/stations", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const stations = await storage.getStations();

    // Add queue information for each station
    const stationsWithQueue = await Promise.all(stations.map(async (station) => {
      const queueLength = await storage.getQueueLength(station.id);
      const userPosition = req.user ? await storage.getQueuePosition(station.id, req.user.id) : null;
      return {
        ...station,
        queueLength,
        userPosition,
        estimatedWaitTime: queueLength * 5, // 5 minutes per session
      };
    }));

    res.json(stationsWithQueue);
  });

  // Session management
  app.post("/api/stations/:id/session", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const station = await storage.getStation(parseInt(req.params.id));

    if (!station) {
      return res.status(404).send("Station not found");
    }

    if (station.status === "in_use") {
      return res.status(400).send("Station is in use");
    }

    const userPosition = await storage.getQueuePosition(station.id, req.user.id);
    if (userPosition !== 1) {
      return res.status(403).send("You are not next in queue");
    }

    const updatedStation = await storage.updateStationSession(station.id, req.user.id);
    res.json(updatedStation);

    // Start session timer updates
    const sessionDuration = 5 * 60 * 1000; // 5 minutes
    const updateInterval = 1000; // Update every second
    const startTime = Date.now();

    const timer = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, (sessionDuration - elapsed) / 1000 / 60); // Convert to minutes
      broadcastSessionTimeUpdate(station.id, remaining);

      if (elapsed >= sessionDuration) {
        clearInterval(timer);
      }
    }, updateInterval);

    // End session after 5 minutes
    setTimeout(async () => {
      await storage.updateStationSession(station.id, null);
      await storage.checkQueueAndUpdateSession(station.id);
      await broadcastQueueUpdate(station.id);
      clearInterval(timer);
      wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({ type: "session_ended", stationId: station.id }));
        }
      });
    }, sessionDuration);
  });

  // Queue management routes
  app.post("/api/stations/:id/queue", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const stationId = parseInt(req.params.id);

    try {
      const position = await storage.joinQueue(stationId, req.user.id);
      await broadcastQueueUpdate(stationId);
      res.json({ position, estimatedWaitTime: position * 5 });
    } catch (error: any) {
      res.status(400).json({ message: error.message });
    }
  });

  app.delete("/api/stations/:id/queue", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const stationId = parseInt(req.params.id);

    try {
      await storage.leaveQueue(stationId, req.user.id);
      await broadcastQueueUpdate(stationId);
      res.sendStatus(200);
    } catch (error: any) {
      res.status(400).json({ message: error.message });
    }
  });

  // Admin routes
  app.post("/api/admin/stations", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const { name, description, rpiHost, rpiPort, rpiAuthToken } = req.body;
    if (!name) return res.status(400).json({ message: "Name is required" });

    try {
      const station = await storage.createStation(name, description, rpiHost, rpiPort, rpiAuthToken);
      res.status(201).json(station);
    } catch (error: any) {
      res.status(500).json({ message: error.message });
    }
  });

  app.delete("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    await storage.deleteStation(parseInt(req.params.id));
    res.sendStatus(200);
  });

  // WebSocket handling with improved authentication and logging
  wss.on("connection", async (ws, req) => {
    console.log("New WebSocket connection attempt");
    console.log("Cookie header:", req.headers.cookie);

    let authenticated = false;
    if (req.headers.cookie) {
      const cookies = parseCookie(req.headers.cookie);
      const sessionId = cookies["connect.sid"];
      console.log("Session ID from cookie:", sessionId);

      if (sessionId) {
        authenticated = true;
        console.log("WebSocket connection authenticated");
      }
    }

    if (!authenticated) {
      console.log("WebSocket connection not authenticated, closing");
      ws.close(1008, "Authentication required");
      return;
    }

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        console.log("Received WebSocket message:", message);
        ws.send(JSON.stringify({ type: "command_received", ...message }));
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
        ws.send(JSON.stringify({ type: "error", message: "Invalid message format" }));
      }
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
    });

    // Send initial connection success message
    ws.send(JSON.stringify({ type: "connected" }));
  });

  return httpServer;
}