import type { Express } from "express";
import { createServer, type Server } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import type { WebSocketMessage as OriginalWebSocketMessage, RPiResponse } from "@shared/schema";
import { parse as parseCookie } from "cookie";
import path from "path";
import fs from "fs/promises";
import express from "express";
import multer from "multer";
import { URL } from "url";

// Define uploadsPath at the top level to use a persistent storage location
const uploadsPath = path.join('/home/runner/workspace/persistent_uploads');
const publicUploadsPath = path.join(process.cwd(), 'public/uploads');

// Ensure upload directories exist
try {
  fs.mkdir(uploadsPath, { recursive: true }).catch(err => console.error('Failed to create persistent uploads dir:', err));
  fs.mkdir(publicUploadsPath, { recursive: true }).catch(err => console.error('Failed to create public uploads dir:', err));
} catch (err) {
  console.error('Error ensuring upload directories exist:', err);
}

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

// Modified to store connection type with the RPi connections
const rpiConnections = new Map<string, { 
  ws: WebSocket; 
  connectionType: 'camera' | 'control' | 'combined' 
}>();

// Map to store UI client connections with their associated RPi IDs
const uiConnections = new Map<string, { ws: WebSocket; rpiId?: string }>();

// Add type for WebSocket messages
interface WebSocketRegistrationMessage {
  type: 'register';
  rpiId: string;
  connectionType?: 'camera' | 'control' | 'combined';
}

interface WebSocketCommandMessage {
  type: 'command';
  rpiId: string;
  command: string;
  direction?: string;
  stepSize?: number;
  stepUnit?: string;
}

type WebSocketMessage = WebSocketRegistrationMessage | WebSocketCommandMessage;


export async function registerRoutes(app: Express): Promise<Server> {
  setupAuth(app);

  // Get all demo station IDs and log them to the console
  const stations = await storage.getStations();
  console.log("=== DEMO STATION IDs ===");
  stations.forEach(station => {
    console.log(`Station ID: ${station.id}, Name: ${station.name}, RPi ID: ${station.rpiId}`);
  });
  console.log("=======================");
  
  // Create a test user if it doesn't exist
  try {
    const testUser = await storage.getUserByUsername("demo@xeryon.com");
    if (!testUser) {
      console.log("Creating demo user for testing...");
      await storage.createUser({
        username: "demo@xeryon.com",
        password: "demoxeryon",
        name: "Demo User",
        isAdmin: false
      });
      console.log("Demo user created successfully");
    } else {
      console.log("Demo user already exists");
    }
  } catch (error) {
    console.error("Error creating demo user:", error);
  }
  
  // Start background job to auto-close sessions that exceed the 5-minute time limit
  const SESSION_DURATION_MS = 5 * 60 * 1000; // 5 minutes in milliseconds
  const checkAndCloseExpiredSessions = async () => {
    try {
      const activeStations = await storage.getStations();
      const now = new Date();
      
      for (const station of activeStations) {
        if (station.status === "in_use" && station.sessionStart) {
          const sessionStartTime = new Date(station.sessionStart);
          const sessionDuration = now.getTime() - sessionStartTime.getTime();
          
          if (sessionDuration >= SESSION_DURATION_MS) {
            console.log(`Auto-closing expired session for station ${station.id} (${station.name})`);
            await storage.updateStationSession(station.id, null);
          }
        }
      }
    } catch (error) {
      console.error("Error in session auto-close job:", error);
    }
  };
  
  // Run the check every minute
  setInterval(checkAndCloseExpiredSessions, 60 * 1000);
  console.log("Session auto-close background job started");

  const httpServer = createServer(app);

  // Create WebSocket servers but don't attach them to paths yet
  const wssUI = new WebSocketServer({ noServer: true });
  const wssRPi = new WebSocketServer({ noServer: true });

  // Handle WebSocket upgrade requests
  httpServer.on('upgrade', (request, socket, head) => {
    const parsedUrl = new URL(request.url!, `http://${request.headers.host}`);
    let pathname = parsedUrl.pathname;

    // Check if the request is from Replit preview, which might add an extra path prefix
    const host = request.headers.host || '';
    if (host.includes('replit.dev') || host.includes('replit.app')) {
      // For deployed endpoints, the full path might include a project-specific prefix
      // Strip it if needed to match our expected paths
      if (pathname.includes('/ws')) {
        pathname = pathname.substring(pathname.indexOf('/ws'));
      } else if (pathname.includes('/appws')) {
        pathname = pathname.substring(pathname.indexOf('/appws'));
      } else if (pathname.includes('/rpi/')) {
        pathname = pathname.substring(pathname.indexOf('/rpi/'));
      }
    }

    console.log(`[WebSocket] Upgrade request received:`, {
      originalPath: parsedUrl.pathname,
      normalizedPath: pathname,
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
    } else if (pathname === '/ws' || pathname === '/appws' || pathname.endsWith('/ws') || pathname.endsWith('/appws')) {
      // Handle the upgrade for UI clients without checking authentication
      // Support both direct paths and paths with prefixes
      console.log("[WebSocket] UI client connection request:", pathname);
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

    // Wait for registration message before adding to connections map
    // The connection will be added when we receive a "register" message with connectionType
    
    // Default to "camera" until we get explicit connection type
    let connectionType: 'camera' | 'control' | 'combined' = 'camera';
    
    // Notify UI clients about new RPi connection
    for (const client of uiConnections.values()) {
      if (client.ws.readyState === WebSocket.OPEN) {
        client.ws.send(JSON.stringify({
          type: "rpi_connected",
          rpiId
        }));
      }
    }

    ws.on("message", async function(data) {
      try {
        const response = JSON.parse(data.toString());

        // Handle ping messages from the RPi (for latency measurement)
        if (response.type === 'ping') {
          console.log(`[RPi ${rpiId}] Received ping message`);
          
          // Send back a pong immediately with the same timestamp
          ws.send(JSON.stringify({
            type: 'pong',
            timestamp: response.timestamp,
            serverTimestamp: new Date().toISOString()
          }));
          
          // Also forward the ping to any connected UI clients for this RPi
          for (const client of uiConnections.values()) {
            if (client.ws.readyState === WebSocket.OPEN && client.rpiId === rpiId) {
              client.ws.send(JSON.stringify({
                type: 'rpi_ping',
                rpiId: rpiId,
                timestamp: response.timestamp
              }));
            }
          }
          return;
        }

        // Log position updates
        if (response.type === 'position_update') {
          console.log(`[RPi ${rpiId}] Position update:`, response.epos);
          
          // Record position in database if there's an active session
          try {
            // Check if there's an active session for this RPi ID
            const stations = await storage.getStations();
            const station = stations.find(s => s.rpiId === rpiId && s.status === "in_use");
            
            if (station && station.currentSessionLogId) {
              // Record the position data
              await storage.recordPosition(station.currentSessionLogId, response.epos);
            }
          } catch (error) {
            console.error(`[RPi ${rpiId}] Error recording position:`, error);
          }
          
          // Forward position updates to relevant UI clients
          for (const client of uiConnections.values()) {
            if (client.ws.readyState === WebSocket.OPEN && client.rpiId === rpiId) {
              client.ws.send(JSON.stringify({
                type: 'position_update',
                rpiId: rpiId,
                epos: response.epos,
                timestamp: response.timestamp || new Date().toISOString()
              }));
              
              // Also dispatch a custom event for position-graph component
              // This dispatches the event to clients as a custom event
              try {
                client.ws.send(JSON.stringify({
                  type: 'custom_event',
                  eventName: 'position-update',
                  data: {
                    position: response.epos,
                    timestamp: response.timestamp || new Date().toISOString(),
                    rpiId: rpiId
                  }
                }));
              } catch (error) {
                console.error(`[RPi ${rpiId}] Error sending position event:`, error);
              }
            }
          }
          return;
        }

        // Ping messages are handled by the dedicated handler above

        // Only log non-camera-frame messages
        if (response.type !== 'camera_frame') {
          console.log(`[RPi ${rpiId}] Message received: ${response.type}`);
        }
        
        // Handle registration message with connection type
        if (response.type === 'register') {
          // Get the connection type from the message
          connectionType = response.connectionType || 'camera';
          console.log(`[RPi ${rpiId}] Registered as ${connectionType} connection`);
          
          // If this is a simulator connection without explicit type, register it as both camera and control
          if (rpiId.includes('RPI') && !response.connectionType) {
            console.log(`[RPi ${rpiId}] Auto-registering as combined connection for simulator`);
            connectionType = 'combined';
          }
          
          // Store the connection with its type
          rpiConnections.set(rpiId, { 
            ws, 
            connectionType 
          });
          
          return;
        }

        // Handle camera frames from RPi
        if (response.type === "camera_frame") {
          // Validate frame data
          if (!response.frame) {
            console.warn(`[RPi ${rpiId}] Received camera_frame without frame data`);
            return;
          }

          // Check if it's already a data URL or just base64
          const isDataUrl = response.frame.startsWith('data:');

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

          // Create the message once to avoid excessive string operations
          const frameMessage = JSON.stringify({
            type: "camera_frame",
            rpiId,
            frame: frameToSend,
            frameNumber: response.frameNumber,
            positionText: response.positionText,
            timestamp: response.timestamp || new Date().toISOString()
          });

          let forwardCount = 0;
          // Only send to UI clients that are subscribed to this RPi's feed
          for (const client of uiConnections.values()) {
            if (client.ws.readyState === WebSocket.OPEN && client.rpiId === rpiId) {
              try {
                client.ws.send(frameMessage);
                forwardCount++;
              } catch (error) {
                console.error(`[RPi ${rpiId}] Error sending frame:`, error);
              }
            }
          }


        } else {
          // Handle RPi command responses - only send to relevant clients
          for (const client of uiConnections.values()) {
            if (client.ws.readyState === WebSocket.OPEN && client.rpiId === rpiId) {
              client.ws.send(JSON.stringify({
                type: "rpi_response",
                rpiId,
                status: response.status,
                message: response.message
              }));
            }
          }
        }
      } catch (err) {
        console.error(`[RPi ${rpiId}] Error handling message:`, err instanceof Error ? err.message : String(err));
      }
    });

    ws.on("close", () => {
      console.log(`[RPi ${rpiId}] Disconnected, connection type: ${connectionType}`);
      
      // Check if there are multiple connections for this RPi
      const existingConnection = rpiConnections.get(rpiId);
      
      // If this was the only connection or if it was the current stored connection, remove it
      if (existingConnection && existingConnection.ws === ws) {
        console.log(`[RPi ${rpiId}] Removing ${connectionType} connection`);
        rpiConnections.delete(rpiId);
        
        // Notify UI clients about RPi disconnection
        for (const client of uiConnections.values()) {
          if (client.ws.readyState === WebSocket.OPEN) {
            client.ws.send(JSON.stringify({
              type: "rpi_disconnected",
              rpiId,
              connectionType
            }));
          }
        }
      } else {
        console.log(`[RPi ${rpiId}] Connection closed but not removing from map as it's not the current connection`);
      }
    });
  });

  // Handle web UI client connections
  wssUI.on("connection", (ws, req) => {
    console.log("[WebSocket] UI client connected");
    const clientId = `ui_${Date.now()}_${Math.random().toString(36).substring(7)}`;
    uiConnections.set(clientId, { ws });

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data.toString()) as WebSocketMessage;
        console.log("[WebSocket] Received UI message:", message);

        // Handle registration messages
        if (message.type === 'register') {
          const rpiId = message.rpiId;
          console.log(`[WebSocket] UI client ${clientId} registered for RPi ${rpiId}`);

          // Update the client's RPi subscription
          uiConnections.set(clientId, { ws, rpiId });

          // Confirm registration
          ws.send(JSON.stringify({
            type: 'registered',
            message: `Successfully registered for RPi ${rpiId}`
          }));
          return;
        }
        
        // Handle ping messages and respond with pong
        if (message.type === 'ping') {
          console.log(`[WebSocket] Received ping from client ${clientId}`);
          
          // Send back pong with the same timestamp
          ws.send(JSON.stringify({
            type: 'pong',
            timestamp: message.timestamp,
            rpiId: message.rpiId
          }));
          return;
        }

        if (!message.rpiId) {
          console.error("[WebSocket] Message missing rpiId:", message);
          ws.send(JSON.stringify({
            type: "error",
            message: "RPi ID is required"
          }));
          return;
        }

        const rpiConnection = rpiConnections.get(String(message.rpiId));

        if (!rpiConnection) {
          console.log(`[WebSocket] RPi ${message.rpiId} not connected`);
          ws.send(JSON.stringify({
            type: "error",
            message: `RPi ${message.rpiId} not connected`
          }));
          return;
        }
        
        // Check if this is a control or combined connection
        if (rpiConnection.connectionType !== 'control' && rpiConnection.connectionType !== 'combined') {
          console.log(`[WebSocket] RPi ${message.rpiId} has no control connection, only ${rpiConnection.connectionType}`);
          ws.send(JSON.stringify({
            type: "error",
            message: `RPi ${message.rpiId} control connection not available - try refreshing the page`,
            details: {
              connectionType: rpiConnection.connectionType
            }
          }));
          return;
        }
        
        // Log the connection type being used to handle the command
        console.log(`[WebSocket] Using ${rpiConnection.connectionType} connection to handle control command for RPi ${message.rpiId}`);
        
        if (rpiConnection.ws.readyState !== WebSocket.OPEN) {
          console.log(`[WebSocket] RPi ${message.rpiId} control connection not ready`);
          ws.send(JSON.stringify({
            type: "error",
            message: `RPi ${message.rpiId} control connection not ready`,
            details: {
              readyState: rpiConnection.ws.readyState
            }
          }));
          return;
        }

        // Forward command to RPi with timestamp and step information
        const commandMessage = {
          type: "command",
          command: message.command || "unknown",
          direction: message.direction || "none",
          stepSize: message.stepSize,
          stepUnit: message.stepUnit,
          timestamp: new Date().toISOString()
        };

        console.log(`[WebSocket] Sending command to RPi ${message.rpiId} control connection:`, {
          type: commandMessage.type,
          command: commandMessage.command,
          direction: commandMessage.direction,
          stepSize: commandMessage.stepSize,
          stepUnit: message.stepUnit,
          rpiId: message.rpiId
        });

        // Send to the WebSocket connection inside the rpiConnection object
        rpiConnection.ws.send(JSON.stringify(commandMessage));

        // Echo back confirmation
        ws.send(JSON.stringify({
          type: "command_sent",
          message: `Command sent to RPi ${message.rpiId}`,
          ...commandMessage
        }));
      } catch (err) {
        console.error("[WebSocket] Failed to parse message:", err instanceof Error ? err.message : String(err));
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
      console.log(`[WebSocket] UI client ${clientId} disconnected`);
      uiConnections.delete(clientId);
    });
  });

  // Ensure uploads directory exists
  await fs.mkdir(uploadsPath, { recursive: true })
    .catch(err => console.error('Error creating uploads directory:', err));

  // Serve uploaded files statically from the persistent location
  app.use('/uploads', express.static(uploadsPath));

  // Make sure the URL path works correctly
  console.log(`Serving uploaded files from: ${uploadsPath}`);

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
  app.get("/api/admin/users", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/users GET");
      return res.sendStatus(403);
    }
    try {
      const allUsers = await storage.getAllUsers();
      res.json(allUsers);
    } catch (error) {
      console.error("Error getting users:", error);
      res.status(500).json({ message: "Failed to fetch users" });
    }
  });

  app.get("/api/admin/session-logs", async (req, res) => {
    if (!isAdmin(req)) {
      console.log("Unauthorized access to /api/admin/session-logs GET");
      return res.sendStatus(403);
    }
    try {
      const logs = await storage.getSessionLogs();
      res.json(logs);
    } catch (error) {
      console.error("Error getting session logs:", error);
      res.status(500).json({ message: "Failed to fetch session logs" });
    }
  });
  
  // NEW: Session replay data endpoint
  app.get("/api/session-replay/:sessionId", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/session-replay/:sessionId GET");
      return res.sendStatus(401);
    }
    
    try {
      const sessionId = parseInt(req.params.sessionId);
      if (isNaN(sessionId)) {
        return res.status(400).json({ message: "Invalid session ID" });
      }
      
      const replayData = await storage.getSessionReplayData(sessionId);
      res.json(replayData);
    } catch (error) {
      console.error("Error getting session replay data:", error);
      res.status(500).json({ message: "Failed to fetch session replay data" });
    }
  });
  
  // NEW: Session analytics endpoint
  app.get("/api/session-analytics", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/session-analytics GET");
      return res.sendStatus(401);
    }
    
    try {
      let timeRange;
      const { startDate, endDate } = req.query;
      
      if (startDate) {
        timeRange = {
          start: new Date(startDate as string),
          end: endDate ? new Date(endDate as string) : new Date()
        };
      }
      
      const analytics = await storage.getSessionAnalytics(timeRange);
      res.json(analytics);
    } catch (error) {
      console.error("Error getting session analytics:", error);
      res.status(500).json({ message: "Failed to fetch session analytics" });
    }
  });
  
  // NEW: System health endpoints
  app.get("/api/system-health/:stationId", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/system-health/:stationId GET");
      return res.sendStatus(401);
    }
    
    try {
      const stationId = parseInt(req.params.stationId);
      if (isNaN(stationId)) {
        return res.status(400).json({ message: "Invalid station ID" });
      }
      
      const { limit } = req.query;
      const healthData = await storage.getSystemHealth(
        stationId, 
        limit ? parseInt(limit as string) : 100
      );
      
      res.json(healthData);
    } catch (error) {
      console.error("Error getting system health data:", error);
      res.status(500).json({ message: "Failed to fetch system health data" });
    }
  });
  
  app.get("/api/system-health/:stationId/latest", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/system-health/:stationId/latest GET");
      return res.sendStatus(401);
    }
    
    try {
      const stationId = parseInt(req.params.stationId);
      if (isNaN(stationId)) {
        return res.status(400).json({ message: "Invalid station ID" });
      }
      
      const healthData = await storage.getLatestSystemHealth(stationId);
      if (!healthData) {
        return res.status(404).json({ message: "No health data found for this station" });
      }
      
      res.json(healthData);
    } catch (error) {
      console.error("Error getting latest system health data:", error);
      res.status(500).json({ message: "Failed to fetch latest system health data" });
    }
  });
  
  // NEW: Technical specifications endpoint
  app.get("/api/technical-specs/:stationId", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/technical-specs/:stationId GET");
      return res.sendStatus(401);
    }
    
    try {
      const stationId = parseInt(req.params.stationId);
      if (isNaN(stationId)) {
        return res.status(400).json({ message: "Invalid station ID" });
      }
      
      const specs = await storage.getTechnicalSpecs(stationId);
      if (!specs) {
        return res.status(404).json({ message: "No technical specifications found for this station" });
      }
      
      res.json(specs);
    } catch (error) {
      console.error("Error getting technical specifications:", error);
      res.status(500).json({ message: "Failed to fetch technical specifications" });
    }
  });
  
  // NEW: Record position data endpoint (for WebSocket integration)
  app.post("/api/record-position", async (req, res) => {
    if (!req.isAuthenticated()) {
      console.log("Unauthorized access to /api/record-position POST");
      return res.sendStatus(401);
    }
    
    try {
      const { sessionLogId, position, commandInfo } = req.body;
      
      if (!sessionLogId || position === undefined) {
        return res.status(400).json({ message: "Session log ID and position are required" });
      }
      
      const positionRecord = await storage.recordPosition(sessionLogId, position, commandInfo);
      res.status(201).json(positionRecord);
    } catch (error) {
      console.error("Error recording position data:", error);
      res.status(500).json({ message: "Failed to record position data" });
    }
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
      const station = await storage.updateStation(stationId, {
        name,
        rpiId
      });
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
        // Ensure uploads directories exist
        await fs.mkdir(uploadsPath, { recursive: true });
        await fs.mkdir(publicUploadsPath, { recursive: true });

        // Generate unique filename with timestamp and original extension
        const filename = `station-${stationId}-${Date.now()}${path.extname(req.file.originalname)}`;
        const persistentFilePath = path.join(uploadsPath, filename);
        const publicFilePath = path.join(publicUploadsPath, filename);

        // Move uploaded file to persistent storage
        await fs.rename(req.file.path, persistentFilePath);
        
        // Copy the file to public directory for serving
        await fs.copyFile(persistentFilePath, publicFilePath);
        
        console.log(`[Image Upload] Saved image to: ${persistentFilePath}`);
        console.log(`[Image Upload] Copied to public: ${publicFilePath}`);

        // Generate public URL path
        const imageUrl = `/uploads/${filename}`;
        console.log(`[Image Upload] Public URL: ${imageUrl}`);

        // Update station with new image URL
        const station = await storage.updateStation(stationId, {
          name: req.body.name,
          rpiId: req.body.rpiId,
          previewImage: imageUrl
        });

        res.json({
          url: imageUrl,
          station
        });
      } catch (error) {
        console.error("Error handling image upload:", error);
        // Clean up temporary file if it exists
        if (req.file?.path) {
          await fs.unlink(req.file.path).catch(err =>
            console.error("Failed to clean up temp file:", err)
          );
        }
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

    // Allow admins to end any session, regular users can only end their own
    const isAdmin = req.user.isAdmin === true;
    if (!isAdmin && station.currentUserId !== req.user.id) {
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