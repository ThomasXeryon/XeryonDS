import session from 'express-session';
import { 
  users, stations, sessionLogs, feedback, 
  positionData, commandLogs, systemHealth, technicalSpecs,
  type User, type InsertUser, type InsertGuestUser, type Station, type SessionLog, 
  type Feedback, type InsertFeedback, type PositionDataPoint,
  type CommandLog, type SystemHealthStatus, type TechnicalSpec,
  type InsertTechSpecs
} from "@shared/schema";
import { db } from "./db";
import { eq, sql, desc, and, or, between, lte, gte, isNull } from "drizzle-orm";
import connectPg from "connect-pg-simple";
import { pool } from "./db";

const PostgresSessionStore = connectPg(session);

interface StationUpdate {
  name?: string;
  isActive?: boolean;
  rpiId?: string;
  previewImage?: string | null;
}

interface IStorage {
  // User management
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  getUserByEmail(email: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  createGuestUser(data: InsertGuestUser): Promise<User>;
  getAllUsers(): Promise<User[]>;
  updateUserAdmin(id: number, isAdmin: boolean): Promise<User>;

  // Station management
  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string, rpiId: string): Promise<Station>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  deleteStation(id: number): Promise<void>;
  updateStation(id: number, update: Partial<StationUpdate>): Promise<Station>;

  // Session management
  getSessionLogs(): Promise<SessionLog[]>;
  createSessionLog(stationId: number, userId: number): Promise<SessionLog>;
  updateSessionLog(id: number, endTime: Date): Promise<SessionLog>;
  incrementCommandCount(sessionLogId: number): Promise<void>;

  // Feedback management
  getFeedback(): Promise<Feedback[]>;
  createFeedback(userId: number, feedback: InsertFeedback): Promise<Feedback>;
  updateFeedbackStatus(id: number, status: "pending" | "reviewed" | "resolved"): Promise<Feedback>;

  // NEW: Position data management
  recordPosition(sessionLogId: number, position: number, commandInfo?: {
    type: string;
    direction?: string;
    stepSize?: number;
    stepUnit?: string;
  }): Promise<PositionDataPoint>;
  getPositionData(sessionLogId: number): Promise<PositionDataPoint[]>;
  getPositionDataByTimeRange(sessionLogId: number, startTime: Date, endTime: Date): Promise<PositionDataPoint[]>;

  // NEW: Command logging
  recordCommand(sessionLogId: number, command: string, direction?: string, 
    stepSize?: number, stepUnit?: string, parameters?: any): Promise<CommandLog>;
  getCommandLogs(sessionLogId: number): Promise<CommandLog[]>;

  // NEW: System health monitoring
  recordSystemHealth(stationId: number, status: string, metrics: {
    connectionLatency?: number;
    cpuUsage?: number;
    memoryUsage?: number;
    uptimeSeconds?: number;
    details?: any;
  }): Promise<SystemHealthStatus>;
  getSystemHealth(stationId: number, limit?: number): Promise<SystemHealthStatus[]>;
  getLatestSystemHealth(stationId: number): Promise<SystemHealthStatus | undefined>;

  // NEW: Technical specifications
  getTechnicalSpecs(stationId: number): Promise<TechnicalSpec | undefined>;
  createOrUpdateTechnicalSpecs(specs: InsertTechSpecs): Promise<TechnicalSpec>;

  // NEW: Session replay and analytics
  getSessionReplayData(sessionId: number): Promise<{
    session: SessionLog;
    positions: PositionDataPoint[];
    commands: CommandLog[];
  }>;
  getSessionAnalytics(timeRange?: { start: Date; end: Date }): Promise<{
    totalSessions: number;
    averageDuration: number;
    commandFrequency: Record<string, number>;
    activeStations: { stationId: number; sessionCount: number }[];
  }>;

  // Session store for authentication
  sessionStore: session.Store;
}

export class DatabaseStorage implements IStorage {
  sessionStore: session.Store;

  constructor() {
    this.sessionStore = new PostgresSessionStore({
      pool,
      createTableIfMissing: true,
    });
  }
  
  // NEW: Position data management
  async recordPosition(
    sessionLogId: number, 
    position: number, 
    commandInfo?: {
      type: string;
      direction?: string;
      stepSize?: number;
      stepUnit?: string;
    }
  ): Promise<PositionDataPoint> {
    try {
      const [positionPoint] = await db.insert(positionData).values({
        sessionLogId,
        position,
        commandType: commandInfo?.type,
        commandDirection: commandInfo?.direction,
        commandStepSize: commandInfo?.stepSize,
        commandStepUnit: commandInfo?.stepUnit,
        timestamp: new Date()
      }).returning();
      return positionPoint;
    } catch (error: any) {
      console.error("Error recording position:", error);
      throw error;
    }
  }

  async getPositionData(sessionLogId: number): Promise<PositionDataPoint[]> {
    try {
      return await db.select()
        .from(positionData)
        .where(eq(positionData.sessionLogId, sessionLogId))
        .orderBy(positionData.timestamp);
    } catch (error) {
      console.error("Error getting position data:", error);
      return [];
    }
  }

  async getPositionDataByTimeRange(
    sessionLogId: number, 
    startTime: Date, 
    endTime: Date
  ): Promise<PositionDataPoint[]> {
    try {
      return await db.select()
        .from(positionData)
        .where(
          and(
            eq(positionData.sessionLogId, sessionLogId),
            between(positionData.timestamp, startTime, endTime)
          )
        )
        .orderBy(positionData.timestamp);
    } catch (error: any) {
      console.error("Error getting position data by time range:", error);
      return [];
    }
  }

  // NEW: Command logging
  async recordCommand(
    sessionLogId: number, 
    command: string, 
    direction?: string, 
    stepSize?: number, 
    stepUnit?: string, 
    parameters?: any
  ): Promise<CommandLog> {
    try {
      const [commandLog] = await db.insert(commandLogs).values({
        sessionLogId,
        command,
        direction,
        stepSize,
        stepUnit,
        parameters,
        timestamp: new Date()
      }).returning();
      return commandLog;
    } catch (error) {
      console.error("Error recording command:", error);
      throw error;
    }
  }

  async getCommandLogs(sessionLogId: number): Promise<CommandLog[]> {
    try {
      return await db.select()
        .from(commandLogs)
        .where(eq(commandLogs.sessionLogId, sessionLogId))
        .orderBy(commandLogs.timestamp);
    } catch (error) {
      console.error("Error getting command logs:", error);
      return [];
    }
  }

  // NEW: System health monitoring
  async recordSystemHealth(
    stationId: number, 
    status: string, 
    metrics: {
      connectionLatency?: number;
      cpuUsage?: number;
      memoryUsage?: number;
      uptimeSeconds?: number;
      details?: any;
    }
  ): Promise<SystemHealthStatus> {
    try {
      const [healthStatus] = await db.insert(systemHealth).values({
        stationId,
        status,
        connectionLatency: metrics.connectionLatency,
        cpuUsage: metrics.cpuUsage,
        memoryUsage: metrics.memoryUsage,
        uptimeSeconds: metrics.uptimeSeconds,
        details: metrics.details,
        timestamp: new Date()
      }).returning();
      return healthStatus;
    } catch (error) {
      console.error("Error recording system health:", error);
      throw error;
    }
  }

  async getSystemHealth(stationId: number, limit: number = 100): Promise<SystemHealthStatus[]> {
    try {
      return await db.select()
        .from(systemHealth)
        .where(eq(systemHealth.stationId, stationId))
        .orderBy(desc(systemHealth.timestamp))
        .limit(limit);
    } catch (error) {
      console.error("Error getting system health:", error);
      return [];
    }
  }

  async getLatestSystemHealth(stationId: number): Promise<SystemHealthStatus | undefined> {
    try {
      const [healthStatus] = await db.select()
        .from(systemHealth)
        .where(eq(systemHealth.stationId, stationId))
        .orderBy(desc(systemHealth.timestamp))
        .limit(1);
      return healthStatus;
    } catch (error) {
      console.error("Error getting latest system health:", error);
      return undefined;
    }
  }

  // NEW: Technical specifications
  async getTechnicalSpecs(stationId: number): Promise<TechnicalSpec | undefined> {
    try {
      const [specs] = await db.select()
        .from(technicalSpecs)
        .where(eq(technicalSpecs.stationId, stationId));
      return specs;
    } catch (error) {
      console.error("Error getting technical specs:", error);
      return undefined;
    }
  }

  async createOrUpdateTechnicalSpecs(specs: InsertTechSpecs): Promise<TechnicalSpec> {
    try {
      // Check if specs exist for this station
      const existingSpecs = await this.getTechnicalSpecs(specs.stationId);
      
      if (existingSpecs) {
        // Update existing specs
        const [updatedSpecs] = await db.update(technicalSpecs)
          .set(specs)
          .where(eq(technicalSpecs.stationId, specs.stationId))
          .returning();
        return updatedSpecs;
      } else {
        // Create new specs
        const [newSpecs] = await db.insert(technicalSpecs)
          .values(specs)
          .returning();
        return newSpecs;
      }
    } catch (error) {
      console.error("Error creating/updating technical specs:", error);
      throw error;
    }
  }

  // NEW: Session replay and analytics
  async getSessionReplayData(sessionId: number): Promise<{
    session: SessionLog;
    positions: PositionDataPoint[];
    commands: CommandLog[];
  }> {
    try {
      // Get session details
      const [session] = await db.select()
        .from(sessionLogs)
        .where(eq(sessionLogs.id, sessionId));
      
      if (!session) {
        throw new Error(`Session with ID ${sessionId} not found`);
      }
      
      // Get position data
      const positions = await this.getPositionData(sessionId);
      
      // Get command logs
      const commands = await this.getCommandLogs(sessionId);
      
      return {
        session,
        positions,
        commands
      };
    } catch (error) {
      console.error("Error getting session replay data:", error);
      throw error;
    }
  }

  async getSessionAnalytics(timeRange?: { start: Date; end: Date }): Promise<{
    totalSessions: number;
    averageDuration: number;
    commandFrequency: Record<string, number>;
    activeStations: { stationId: number; sessionCount: number }[];
  }> {
    try {
      // Query to get sessions in the time range
      let query = db.select().from(sessionLogs);
      
      if (timeRange) {
        query = query.where(
          and(
            gte(sessionLogs.startTime, timeRange.start),
            timeRange.end ? lte(sessionLogs.startTime, timeRange.end) : undefined
          )
        );
      }
      
      const sessions = await query;
      
      // Calculate total sessions
      const totalSessions = sessions.length;
      
      // Calculate average duration
      let totalDuration = 0;
      let completedSessions = 0;
      
      for (const session of sessions) {
        if (session.startTime && session.endTime) {
          const duration = session.endTime.getTime() - session.startTime.getTime();
          totalDuration += duration;
          completedSessions++;
        }
      }
      
      const averageDuration = completedSessions ? totalDuration / completedSessions : 0;
      
      // Get command frequency
      const commandFrequency: Record<string, number> = {};
      
      // Get session IDs for the time range
      const sessionIds = sessions.map(s => s.id);
      
      // Get commands for these sessions
      if (sessionIds.length > 0) {
        const commands = await db.select()
          .from(commandLogs)
          .where(
            or(
              ...sessionIds.map(id => eq(commandLogs.sessionLogId, id))
            )
          );
        
        // Count command frequency
        for (const cmd of commands) {
          if (!commandFrequency[cmd.command]) {
            commandFrequency[cmd.command] = 0;
          }
          commandFrequency[cmd.command]++;
        }
      }
      
      // Get active stations
      const stationCounts: Record<string, number> = {};
      
      for (const session of sessions) {
        const stationIdStr = session.stationId.toString();
        if (!stationCounts[stationIdStr]) {
          stationCounts[stationIdStr] = 0;
        }
        stationCounts[stationIdStr]++;
      }
      
      const activeStations = Object.entries(stationCounts).map(([stationId, count]) => ({
        stationId: parseInt(stationId),
        sessionCount: count
      })).sort((a, b) => b.sessionCount - a.sessionCount);
      
      return {
        totalSessions,
        averageDuration,
        commandFrequency,
        activeStations
      };
    } catch (error) {
      console.error("Error getting session analytics:", error);
      throw error;
    }
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

  async getUserByEmail(email: string): Promise<User | undefined> {
    try {
      const [user] = await db.select().from(users).where(eq(users.email, email));
      return user;
    } catch (error) {
      console.error("Error getting user by email:", error);
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

  async createGuestUser(data: InsertGuestUser): Promise<User> {
    try {
      // Generate a random username based on the email
      const emailPrefix = data.email.split('@')[0];
      const timestamp = Date.now().toString().slice(-6);
      const randomUsername = `guest_${emailPrefix}_${timestamp}`;
      
      // Create guest user (no password, has isGuest flag)
      const [user] = await db.insert(users).values({
        username: randomUsername,
        email: data.email,
        isGuest: true,
        isAdmin: false
      }).returning();
      
      return user;
    } catch (error) {
      console.error("Error creating guest user:", error);
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
    try {
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
        // Find active session logs for this station
        const activeLogs = await db
          .select()
          .from(sessionLogs)
          .where(eq(sessionLogs.stationId, id))
          .where(sql`${sessionLogs.endTime} IS NULL`);

        // Close any active sessions
        for (const log of activeLogs) {
          await this.updateSessionLog(log.id, new Date());
        }
      }

      return station;
    } catch (error: any) {
      console.error("Error updating station session:", error);
      throw error;
    }
  }

  async deleteStation(id: number): Promise<void> {
    await db
      .update(stations)
      .set({ isActive: false })
      .where(eq(stations.id, id));
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
    } catch (error: any) {
      console.error("Error updating station:", error);
      throw new Error(`Failed to update station: ${error?.message || 'Unknown error'}`);
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
    try {
      const [log] = await db
        .update(sessionLogs)
        .set({ endTime })
        .where(eq(sessionLogs.id, id))
        .returning();
      return log;
    } catch (error: any) {
      console.error("Error updating session log:", error);
      throw error;
    }
  }

  async incrementCommandCount(sessionLogId: number): Promise<void> {
    try {
      await db
        .update(sessionLogs)
        .set({
          commandCount: sql`${sessionLogs.commandCount} + 1`
        })
        .where(eq(sessionLogs.id, sessionLogId));
    } catch (error: any) {
      console.error("Error incrementing command count:", error);
      throw error;
    }
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