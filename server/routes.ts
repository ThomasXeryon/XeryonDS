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

  // WebSocket authentication and message handling
  wss.on("connection", (ws, req) => {
    let authenticated = false;

    // Authenticate WebSocket connection using session cookie
    if (req.headers.cookie) {
      const cookies = parseCookie(req.headers.cookie);
      const sessionId = cookies["session_id"]; // Match the custom session name
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
        // Forward message to RPI control system
        console.log("Received command:", message);

        // Echo back confirmation
        ws.send(JSON.stringify({ type: "command_received", ...message }));
      } catch (err) {
        console.error("Failed to parse message:", err);
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