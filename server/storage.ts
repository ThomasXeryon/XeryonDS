import type { SessionStore } from 'express-session';
import { users, stations, sessionLogs, feedback, type User, type InsertUser, type Station, type SessionLog, type Feedback, type InsertFeedback } from "@shared/schema";
import { db } from "./db";
import { eq, sql } from "drizzle-orm";
import session from "express-session";
import connectPg from "connect-pg-simple";
import { pool } from "./db";

const PostgresSessionStore = connectPg(session);

interface StationUpdate {
  name: string;
  ipAddress: string;
  port: string;
  secretKey: string;
}

interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;
  updateUserAdmin(id: number, isAdmin: boolean): Promise<User>;

  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string, ipAddress: string, port: string, secretKey: string): Promise<Station>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  deleteStation(id: number): Promise<void>;
  updateStation(id: number, update: StationUpdate): Promise<Station>;

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

  async createStation(name: string, ipAddress: string, port: string, secretKey: string): Promise<Station> {
    const [station] = await db
      .insert(stations)
      .values({
        name,
        ipAddress,
        port,
        secretKey,
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
    await db
      .update(stations)
      .set({ isActive: false })
      .where(eq(stations.id, id));
  }

  async updateStation(id: number, update: StationUpdate): Promise<Station> {
    const [station] = await db
      .update(stations)
      .set(update)
      .where(eq(stations.id, id))
      .returning();
    return station;
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
}

export const storage = new DatabaseStorage();