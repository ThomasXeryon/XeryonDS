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

  // Queue management routes
  app.post("/api/stations/:id/queue", async (req, res) => {
    if (!req.isAuthenticated()) return res.sendStatus(401);
    const stationId = parseInt(req.params.id);

    try {
      const position = await storage.joinQueue(stationId, req.user.id);
      await broadcastQueueUpdate(stationId);
      res.json({ position, estimatedWaitTime: position * 5 });
    } catch (error) {
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
    } catch (error) {
      res.status(400).json({ message: error.message });
    }
  });

  // Existing feedback routes...
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

  // Modified session management
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

    // End session after 5 minutes
    setTimeout(async () => {
      await storage.updateStationSession(station.id, null);
      await storage.checkQueueAndUpdateSession(station.id);
      await broadcastQueueUpdate(station.id);
      wss.clients.forEach((client) => {
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

  // WebSocket handling
  wss.on("connection", (ws, req) => {
    let authenticated = false;

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
        console.log("Received command:", message);
        ws.send(JSON.stringify({ type: "command_received", ...message }));
      } catch (err) {
        console.error("Failed to parse message:", err);
        ws.send(JSON.stringify({ type: "error", message: "Invalid message format" }));
      }
    });

    ws.on("error", (error) => {
      console.error("WebSocket error:", error);
    });

    ws.send(JSON.stringify({ type: "connected" }));
  });

  // Other admin routes
  app.post("/api/admin/stations", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const { name } = req.body;
    if (!name) return res.status(400).json({ message: "Name is required" });

    const station = await storage.createStation(name);
    res.status(201).json(station);
  });

  app.delete("/api/admin/stations/:id", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    await storage.deleteStation(parseInt(req.params.id));
    res.sendStatus(200);
  });


  return httpServer;
}