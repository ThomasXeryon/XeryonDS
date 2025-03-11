import type { SessionStore } from 'express-session';
import { users, stations, sessionLogs, feedback, type User, type InsertUser, type Station, type SessionLog, type Feedback, type InsertFeedback } from "@shared/schema";
import { db } from "./db";
import { eq, sql } from "drizzle-orm";
import session from "express-session";
import connectPg from "connect-pg-simple";
import { pool } from "./db";

const PostgresSessionStore = connectPg(session);

interface StationUpdate {
  name?: string;
  rpiId?: string;
  previewImage?: string;
  isActive?: boolean;
}

interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;
  updateUserAdmin(id: number, isAdmin: boolean): Promise<User>;

  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string, rpiId: string): Promise<Station>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  deleteStation(id: number): Promise<void>;
  updateStation(id: number, update: Partial<StationUpdate>): Promise<Station>;

  getSessionLogs(): Promise<SessionLog[]>;
  createSessionLog(stationId: number, userId: number): Promise<SessionLog>;
  updateSessionLog(id: number, endTime: Date): Promise<SessionLog>;
  incrementCommandCount(sessionLogId: number): Promise<void>;

  getFeedback(): Promise<Feedback[]>;
  createFeedback(userId: number, feedback: InsertFeedback): Promise<Feedback>;
  updateFeedbackStatus(id: number, status: "pending" | "reviewed" | "resolved"): Promise<Feedback>;

  sessionStore: SessionStore;
}

export class DatabaseStorage implements IStorage {
  sessionStore: SessionStore;

  constructor() {
    this.sessionStore = new PostgresSessionStore({
      pool,
      createTableIfMissing: true,
    });
  }

  async getUser(id: number): Promise<User | undefined> {
    try {
      const [user] = await db.select().from(users).where(eq(users.id, id));
      return user;
    } catch (error) {
      console.error("Error getting user:", error);
      return undefined;
    }
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    try {
      const [user] = await db.select().from(users).where(eq(users.username, username));
      return user;
    } catch (error) {
      console.error("Error getting user by username:", error);
      return undefined;
    }
  }

  async getAllUsers(): Promise<User[]> {
    return await db.select().from(users);
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    try {
      const [user] = await db.insert(users).values(insertUser).returning();
      return user;
    } catch (error) {
      console.error("Error creating user:", error);
      throw error;
    }
  }

  async getStations(): Promise<Station[]> {
    try {
      // Only return active stations for regular users
      return await db.select().from(stations).where(eq(stations.isActive, true));
    } catch (error) {
      console.error("Error getting stations:", error);
      return [];
    }
  }

  async getStation(id: number): Promise<Station | undefined> {
    const [station] = await db.select().from(stations).where(eq(stations.id, id));
    return station;
  }

  async createStation(name: string, rpiId: string): Promise<Station> {
    const [station] = await db
      .insert(stations)
      .values({
        name,
        rpiId,
        status: "available",
        isActive: true,
      })
      .returning();
    return station;
  }

  async updateStationSession(id: number, userId: number | null): Promise<Station> {
    const [station] = await db
      .update(stations)
      .set({
        status: userId ? "in_use" : "available",
        currentUserId: userId,
        sessionStart: userId ? new Date() : null,
      })
      .where(eq(stations.id, id))
      .returning();

    if (userId) {
      await this.createSessionLog(id, userId);
    } else {
      const [log] = await db
        .select()
        .from(sessionLogs)
        .where(eq(sessionLogs.stationId, id))
        .where(sql`${sessionLogs.endTime} IS NULL`);

      if (log) {
        await this.updateSessionLog(log.id, new Date());
      }
    }

    return station;
  }

  async deleteStation(id: number): Promise<void> {
    try {
      // First, check if the station exists
      const station = await this.getStation(id);
      if (!station) {
        console.log(`Station with ID ${id} not found, nothing to delete.`);
        return;
      }

      console.log(`Deleting station with ID ${id} and RPI ID ${station.rpiId}...`);

      // Delete any session logs related to this station
      await db.delete(sessionLogs).where(eq(sessionLogs.stationId, id));

      // Finally delete the station itself
      await db.delete(stations).where(eq(stations.id, id));

      console.log(`Station with ID ${id} successfully deleted.`);
    } catch (error) {
      console.error(`Error deleting station with ID ${id}:`, error);
      throw error;
    }
  }

  async updateStation(id: number, update: Partial<StationUpdate>): Promise<Station> {
    // Remove undefined values from the update object
    const filteredUpdate = Object.fromEntries(
      Object.entries(update).filter(([_, value]) => value !== undefined)
    );

    // Ensure we have values to update
    if (Object.keys(filteredUpdate).length === 0) {
      throw new Error("No valid update values provided");
    }

    try {
      const [station] = await db
        .update(stations)
        .set(filteredUpdate)
        .where(eq(stations.id, id))
        .returning();
      return station;
    } catch (error) {
      console.error("Error updating station:", error);
      throw new Error(`Failed to update station: ${error.message}`);
    }
  }

  async getSessionLogs(): Promise<SessionLog[]> {
    return await db.select().from(sessionLogs);
  }

  async createSessionLog(stationId: number, userId: number): Promise<SessionLog> {
    const [log] = await db
      .insert(sessionLogs)
      .values({
        stationId,
        userId,
        startTime: new Date(),
        commandCount: 0,
      })
      .returning();
    return log;
  }

  async updateSessionLog(id: number, endTime: Date): Promise<SessionLog> {
    const [log] = await db
      .update(sessionLogs)
      .set({ endTime })
      .where(eq(sessionLogs.id, id))
      .returning();
    return log;
  }

  async incrementCommandCount(sessionLogId: number): Promise<void> {
    await db
      .update(sessionLogs)
      .set({
        commandCount: sql`${sessionLogs.commandCount} + 1`
      })
      .where(eq(sessionLogs.id, sessionLogId));
  }

  async getFeedback(): Promise<Feedback[]> {
    return await db.select().from(feedback);
  }

  async createFeedback(userId: number, feedbackData: InsertFeedback): Promise<Feedback> {
    const [result] = await db
      .insert(feedback)
      .values({
        userId,
        ...feedbackData,
        createdAt: new Date(),
        status: "pending",
      })
      .returning();
    return result;
  }

  async updateFeedbackStatus(id: number, status: "pending" | "reviewed" | "resolved"): Promise<Feedback> {
    const [result] = await db
      .update(feedback)
      .set({ status })
      .where(eq(feedback.id, id))
      .returning();
    return result;
  }
  async updateUserAdmin(id: number, isAdmin: boolean): Promise<User> {
    try {
      const [user] = await db
        .update(users)
        .set({ isAdmin })
        .where(eq(users.id, id))
        .returning();
      return user;
    } catch (error) {
      console.error("Error updating user admin status:", error);
      throw error;
    }
  }

  // Utility function to clean up orphaned stations
  async cleanupOrphanedStations(): Promise<void> {
    try {
      console.log("Starting cleanup of orphaned stations...");
      
      // Get all stations, regardless of active status
      const allStations = await db.select().from(stations);
      
      console.log(`Found ${allStations.length} total stations in database.`);
      let deletedCount = 0;

      // Get all connected RPi IDs (stations that actually exist)
      const connectedRpiIds = Array.from(global.rpiConnections?.keys() || []);
      console.log(`Currently connected RPi IDs: ${connectedRpiIds.join(', ') || 'none'}`);

      for (const station of allStations) {
        // Delete station if it has missing data or doesn't exist
        if (!station.name || !station.rpiId) {
          console.log(`Deleting invalid station ID ${station.id} with missing name or rpiId`);
          await this.deleteStation(station.id);
          deletedCount++;
        }
      }

      console.log(`Cleanup complete. Deleted ${deletedCount} orphaned stations.`);
      return;
    } catch (error) {
      console.error("Error during station cleanup:", error);
      throw error;
    }
  }
}

export const storage = new DatabaseStorage();

// Delete a station
export async function deleteStation(stationId: number) {
  // First find the station to get its details
  const stationToDelete = await db
    .select()
    .from(stations)
    .where(eq(stations.id, stationId))
    .then((rows) => rows[0]);

  // Then delete it
  const result = await db.delete(stations).where(eq(stations.id, stationId));

  // Log deletion for debugging
  console.log(`Deleted station ${stationId}, affected rows: ${result.rowCount}`);

  return result;
}