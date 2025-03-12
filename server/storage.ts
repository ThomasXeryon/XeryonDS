// Extend WebSocket type to include rpiId property
interface AppWebSocket extends WebSocket {
  rpiId?: string;
}

// WebSocket connections
export const rpiConnections: Map<string, WebSocket> = new Map();
export const appClients: Set<AppWebSocket> = new Set();

// Create a storage object to export
export const storage = {
  sessionStore: null,
  
  // User related methods
  async getUser(id: number) {
    // Implementation needed
    return null;
  },
  
  async getUserByUsername(username: string) {
    // Implementation needed
    return null;
  },
  
  async createUser(userData: any) {
    // Implementation needed
    return userData;
  }
};