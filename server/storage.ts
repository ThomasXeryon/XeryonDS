
import session, { SessionData, Store } from 'express-session';
import { drizzle } from 'drizzle-orm/postgres-js';
import { eq, and, isNull, sql } from 'drizzle-orm';
import postgres from 'postgres';
import {
  users,
  stations,
  sessionLogs,
  User,
  Station,
  InsertUser as NewUser
} from '@shared/schema';
import { PostgresJsDatabase } from 'drizzle-orm/postgres-js';

interface StationUpdate {
  name?: string;
  isActive?: boolean;
  previewImage?: string;
}

interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: NewUser): Promise<User>;
  updateUserAdmin(userId: number, isAdmin: boolean): Promise<User>;
  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string, rpiId: string): Promise<Station>;
  updateStation(id: number, update: Partial<StationUpdate>): Promise<Station>;
  deleteStation(id: number): Promise<void>;
  updateStationSession(stationId: number, userId: number | null): Promise<Station>;
  get sessionStore(): Store;
  db: PostgresJsDatabase;
}

class Storage implements IStorage {
  private client;
  db: PostgresJsDatabase;
  sessionStore: Store;

  constructor() {
    const connectionString = process.env.DATABASE_URL || 
      'postgresql://ep-sweet-queen-a53kyxy1.us-east-2.aws.neon.tech:5432/neondb?sslmode=require';
      
    console.log(`Connecting to database at ${connectionString}`);
    
    this.client = postgres(connectionString, {
      max: 10,
      ssl: true,
    });
    
    this.db = drizzle(this.client);
    
    // Create a basic in-memory session store for development
    const MemoryStore = require('memorystore')(session);
    this.sessionStore = new MemoryStore({
      checkPeriod: 86400000 // prune expired entries every 24h
    });
  }

  async getUser(id: number): Promise<User | undefined> {
    try {
      const result = await this.db.select()
        .from(users)
        .where(eq(users.id, id))
        .limit(1);
      
      return result[0];
    } catch (error) {
      console.error(`Failed to get user: ${error}`);
      throw error;
    }
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    try {
      const result = await this.db.select()
        .from(users)
        .where(eq(users.username, username))
        .limit(1);
      
      return result[0];
    } catch (error) {
      console.error(`Failed to get user by username: ${error}`);
      throw error;
    }
  }

  async createUser(user: NewUser): Promise<User> {
    try {
      const result = await this.db.insert(users)
        .values(user)
        .returning();
      
      return result[0];
    } catch (error) {
      console.error(`Failed to create user: ${error}`);
      throw error;
    }
  }

  async updateUserAdmin(userId: number, isAdmin: boolean): Promise<User> {
    try {
      const result = await this.db.update(users)
        .set({ isAdmin })
        .where(eq(users.id, userId))
        .returning();
      
      return result[0];
    } catch (error) {
      console.error(`Failed to update user admin status: ${error}`);
      throw error;
    }
  }

  async getStations(): Promise<Station[]> {
    try {
      return await this.db.select().from(stations);
    } catch (error) {
      console.error(`Failed to get stations: ${error}`);
      throw error;
    }
  }

  async getStation(id: number): Promise<Station | undefined> {
    try {
      const result = await this.db.select()
        .from(stations)
        .where(eq(stations.id, id))
        .limit(1);
      
      return result[0];
    } catch (error) {
      console.error(`Failed to get station: ${error}`);
      throw error;
    }
  }

  async createStation(name: string, rpiId: string): Promise<Station> {
    try {
      const result = await this.db.insert(stations)
        .values({
          name,
          rpiId,
          status: 'available',
          currentUserId: null,
          isActive: true,
        })
        .returning();
      
      return result[0];
    } catch (error) {
      console.error(`Failed to create station: ${error}`);
      throw error;
    }
  }

  async updateStation(id: number, update: Partial<StationUpdate>): Promise<Station> {
    try {
      const result = await this.db.update(stations)
        .set(update)
        .where(eq(stations.id, id))
        .returning();
      
      return result[0];
    } catch (error: any) {
      console.error(`Failed to update station: ${error.message}`);
      throw new Error(`Failed to update station: ${error.message}`);
    }
  }

  async deleteStation(id: number): Promise<void> {
    try {
      await this.db.delete(stations)
        .where(eq(stations.id, id));
    } catch (error) {
      console.error(`Failed to delete station: ${error}`);
      throw error;
    }
  }

  async updateStationSession(stationId: number, userId: number | null): Promise<Station> {
    try {
      // Start a new session log if a user is claiming the station
      if (userId) {
        // Check if there's already an active session for this station
        const activeSessions = await this.db.select()
          .from(sessionLogs)
          .where(
            and(
              eq(sessionLogs.stationId, stationId),
              isNull(sessionLogs.endTime)
            )
          );

        // If no active session, create a new one
        if (activeSessions.length === 0) {
          await this.db.insert(sessionLogs)
            .values({
              stationId,
              userId,
              startTime: new Date(),
              endTime: null,
              commandCount: 0
            });
        }

        // Update the station status
        const result = await this.db.update(stations)
          .set({
            status: 'in_use',
            currentUserId: userId
          })
          .where(eq(stations.id, stationId))
          .returning();
          
        return result[0];
      } else {
        // End the session log
        await this.db.update(sessionLogs)
          .set({ endTime: new Date() })
          .where(
            and(
              eq(sessionLogs.stationId, stationId),
              isNull(sessionLogs.endTime)
            )
          );

        // Update the station status
        const result = await this.db.update(stations)
          .set({
            status: 'available',
            currentUserId: null
          })
          .where(eq(stations.id, stationId))
          .returning();
          
        return result[0];
      }
    } catch (error) {
      console.error(`Failed to update station session: ${error}`);
      throw error;
    }
  }
}

export const storage = new Storage();
