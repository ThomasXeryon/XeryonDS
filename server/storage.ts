import { db } from './db';
import { eq } from 'drizzle-orm';
import { users } from '@shared/schema';
import WebSocket from 'ws';

// Define User type
interface User {
  id: number;
  username: string;
  isAdmin: boolean;
}

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

  async createUser(user: {
    username: string;
    password: string;
  }): Promise<User> {
    const result = await db
      .insert(users)
      .values(user)
      .returning({ id: users.id, username: users.username, isAdmin: users.isAdmin });

    return result[0];
  },

  async updateUserAdmin(userId: number, isAdmin: boolean): Promise<void> {
    await db
      .update(users)
      .set({ isAdmin })
      .where(eq(users.id, userId));
  },
};