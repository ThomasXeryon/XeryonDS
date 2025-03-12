// Extend WebSocket type to include rpiId property
interface AppWebSocket extends WebSocket {
  rpiId?: string;
}

// WebSocket connections
export const rpiConnections: Map<string, WebSocket> = new Map();
export const appClients: Set<AppWebSocket> = new Set();