
import express, { type Express } from "express";
import { Server } from "http";
import WebSocket from "ws";
import { log } from "./vite";
import { storage } from "./storage";
import expressWs from "express-ws";

// WebSocket connections
interface AppWebSocket extends WebSocket {
  rpiId?: string;
}

const appClients: Set<AppWebSocket> = new Set(); // Browser clients
const rpiConnections: Map<string, WebSocket> = new Map(); // RPi connections (ID -> WebSocket)

export async function registerRoutes(app: Express): Promise<Server> {
  const server = new Server(app);
  const wsInstance = expressWs(app, server);

  // API routes
  app.get("/api/health", (req, res) => {
    res.json({ status: "OK" });
  });

  // WebSocket handling for RPi connections
  app.ws('/rpi/:id', (ws, req) => {
    const rpiId = req.params.id;
    console.log(`RPi ${rpiId} connected via WebSocket`);

    // Store the RPi connection
    rpiConnections.set(rpiId, ws);

    ws.on('message', async (message) => {
      try {
        // Parse the message - could be JSON or binary (image data)
        if (message instanceof Buffer) {
          // It's binary data (likely an image)
          // Convert buffer to base64 for sending to clients
          const base64Frame = `data:image/jpeg;base64,${message.toString('base64')}`;

          // Only send to clients that are connected to this specific RPI
          appClients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN && client.rpiId === rpiId) {
              client.send(JSON.stringify({
                type: 'camera_frame',
                rpiId,
                frame: base64Frame,
                timestamp: new Date().toISOString()
              }));
            }
          });
        }
      } catch (error) {
        console.error('Error processing RPi message:', error);
      }
    });

    ws.on('close', () => {
      console.log(`RPi ${rpiId} disconnected`);
      rpiConnections.delete(rpiId);
    });

    ws.on('error', (error) => {
      console.error(`Error with RPi ${rpiId} connection:`, error);
      rpiConnections.delete(rpiId);
    });
  });

  // WebSocket handling for browser clients
  app.ws('/appws', (ws: AppWebSocket, req) => {
    console.log(`Browser client connected via WebSocket`);

    // Store the client connection
    appClients.add(ws);

    // Send initial connection status for all RPis
    const status = Array.from(rpiConnections.keys()).map(id => ({
      rpiId: id,
      status: 'connected'
    }));

    ws.send(JSON.stringify({
      type: 'connection_status',
      status
    }));

    ws.on('message', (message) => {
      try {
        const data = JSON.parse(message.toString());
        console.log(`Received message from browser client:`, data);

        // Handle different message types
        if (data.type === 'command' && data.rpiId && data.command) {
          // Store which RPI this client is watching/controlling
          ws.rpiId = data.rpiId;

          const rpiWs = rpiConnections.get(data.rpiId);
          if (rpiWs && rpiWs.readyState === WebSocket.OPEN) {
            rpiWs.send(JSON.stringify(data));
          } else {
            ws.send(JSON.stringify({
              type: 'error',
              message: `RPi ${data.rpiId} is not connected`
            }));
          }
        } else if (data.type === 'watch_station' && data.rpiId) {
          // Explicit message to watch a specific station
          ws.rpiId = data.rpiId;
          console.log(`Client now watching RPi ${data.rpiId}`);
        }
      } catch (error) {
        console.error('Error processing client message:', error);
      }
    });

    ws.on('close', () => {
      console.log('Browser client disconnected');
      appClients.delete(ws);
    });
  });

  return server;
}
