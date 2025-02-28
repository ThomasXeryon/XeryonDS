import { users, stations, sessionLogs, stationQueue, type User, type InsertUser, type Station, type SessionLog, type StationQueue } from "@shared/schema";
import session from "express-session";
import createMemoryStore from "memorystore";
import { hashPassword } from "@shared/auth-utils";

const MemoryStore = createMemoryStore(session);

//Inferring types based on context.  This is an assumption, you might need to adjust based on your actual schema.
type Feedback = {
    id: number;
    userId: number;
    type: string;
    message: string;
    createdAt: Date;
    status: "pending" | "reviewed" | "resolved";
};

type InsertFeedback = Omit<Feedback, 'id' | 'createdAt' | 'status'>;

export interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;

  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string, description?: string | null, rpiHost?: string | null, rpiPort?: number | null, rpiAuthToken?: string | null): Promise<Station>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  deleteStation(id: number): Promise<void>;

  // Queue operations
  joinQueue(stationId: number, userId: number): Promise<number>; // Returns position in queue
  leaveQueue(stationId: number, userId: number): Promise<void>;
  getQueuePosition(stationId: number, userId: number): Promise<number | null>;
  getQueueLength(stationId: number): Promise<number>;
  checkQueueAndUpdateSession(stationId: number): Promise<void>;

  getSessionLogs(): Promise<SessionLog[]>;
  createSessionLog(stationId: number, userId: number): Promise<SessionLog>;
  updateSessionLog(id: number, endTime: Date): Promise<SessionLog>;
  incrementCommandCount(sessionLogId: number): Promise<void>;

  getFeedback(): Promise<Feedback[]>;
  createFeedback(userId: number, feedback: InsertFeedback): Promise<Feedback>;
  updateFeedbackStatus(id: number, status: "pending" | "reviewed" | "resolved"): Promise<Feedback>;

  sessionStore: session.SessionStore;
}

export class MemStorage implements IStorage {
  private users: Map<number, User>;
  private stations: Map<number, Station>;
  private sessionLogs: Map<number, SessionLog>;
  private feedback: Map<number, Feedback>;
  private queue: Map<number, StationQueue[]>; // stationId -> queue entries
  private currentId: number;
  sessionStore: session.SessionStore;

  constructor() {
    this.users = new Map();
    this.stations = new Map();
    this.sessionLogs = new Map();
    this.feedback = new Map();
    this.queue = new Map();
    this.sessionStore = new MemoryStore({
      checkPeriod: 86400000,
    });

    // Set initial ID to be higher than any pre-initialized data
    this.currentId = 1;

    // Initialize admin user first
    const adminUser: User = {
      id: this.currentId++,
      username: "admin",
      password: hashPassword("adminpass"),
      isAdmin: true,
    };
    this.users.set(adminUser.id, adminUser);

    // Initialize demo stations
    const station1: Station = {
      id: this.currentId++,
      name: "Demo Station 1",
      status: "available",
      currentUserId: null,
      sessionStart: null,
      isActive: true,
    };

    const station2: Station = {
      id: this.currentId++,
      name: "Demo Station 2",
      status: "available",
      currentUserId: null,
      sessionStart: null,
      isActive: true,
    };

    this.stations.set(station1.id, station1);
    this.stations.set(station2.id, station2);
    this.queue.set(station1.id, []);
    this.queue.set(station2.id, []);
  }

  async getUser(id: number): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find(
      (user) => user.username === username,
    );
  }

  async getAllUsers(): Promise<User[]> {
    return Array.from(this.users.values());
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const id = this.currentId++;
    const user: User = { ...insertUser, id, isAdmin: false };
    this.users.set(id, user);
    return user;
  }

  async getStations(): Promise<Station[]> {
    return Array.from(this.stations.values()).filter(station => station.isActive);
  }

  async getStation(id: number): Promise<Station | undefined> {
    return this.stations.get(id);
  }

  async createStation(
    name: string,
    description?: string | null,
    rpiHost?: string | null,
    rpiPort?: number | null,
    rpiAuthToken?: string | null
  ): Promise<Station> {
    const id = this.currentId++;
    const station: Station = {
      id,
      name,
      description,
      status: "available",
      currentUserId: null,
      sessionStart: null,
      isActive: true,
      rpiHost,
      rpiPort,
      rpiAuthToken,
    };
    this.stations.set(id, station);
    this.queue.set(id, []);
    return station;
  }

  async updateStationSession(id: number, userId: number | null): Promise<Station> {
    const station = await this.getStation(id);
    if (!station) throw new Error("Station not found");

    const updatedStation: Station = {
      ...station,
      status: userId ? "in_use" : "available",
      currentUserId: userId,
      sessionStart: userId ? new Date() : null,
    };

    this.stations.set(id, updatedStation);

    if (userId) {
      // Create session log when starting session
      await this.createSessionLog(id, userId);
    } else {
      // Update session log when ending session
      const log = Array.from(this.sessionLogs.values())
        .find(log => log.stationId === id && !log.endTime);
      if (log) {
        await this.updateSessionLog(log.id, new Date());
      }
    }

    return updatedStation;
  }

  async deleteStation(id: number): Promise<void> {
    const station = await this.getStation(id);
    if (station) {
      station.isActive = false;
      this.stations.set(id, station);
    }
  }

  async getSessionLogs(): Promise<SessionLog[]> {
    return Array.from(this.sessionLogs.values());
  }

  async createSessionLog(stationId: number, userId: number): Promise<SessionLog> {
    const id = this.currentId++;
    const log: SessionLog = {
      id,
      stationId,
      userId,
      startTime: new Date(),
      endTime: null,
      commandCount: 0,
    };
    this.sessionLogs.set(id, log);
    return log;
  }

  async updateSessionLog(id: number, endTime: Date): Promise<SessionLog> {
    const log = this.sessionLogs.get(id);
    if (!log) throw new Error("Session log not found");

    const updatedLog: SessionLog = {
      ...log,
      endTime,
    };
    this.sessionLogs.set(id, updatedLog);
    return updatedLog;
  }

  async incrementCommandCount(sessionLogId: number): Promise<void> {
    const log = this.sessionLogs.get(sessionLogId);
    if (!log) throw new Error("Session log not found");

    log.commandCount++;
    this.sessionLogs.set(sessionLogId, log);
  }

  async getFeedback(): Promise<Feedback[]> {
    return Array.from(this.feedback.values());
  }

  async createFeedback(userId: number, insertFeedback: InsertFeedback): Promise<Feedback> {
    const id = this.currentId++;
    const feedback: Feedback = {
      id,
      userId,
      ...insertFeedback,
      createdAt: new Date(),
      status: "pending"
    };
    this.feedback.set(id, feedback);
    return feedback;
  }

  async updateFeedbackStatus(id: number, status: "pending" | "reviewed" | "resolved"): Promise<Feedback> {
    const feedback = this.feedback.get(id);
    if (!feedback) throw new Error("Feedback not found");

    const updatedFeedback: Feedback = {
      ...feedback,
      status
    };
    this.feedback.set(id, updatedFeedback);
    return updatedFeedback;
  }

  async joinQueue(stationId: number, userId: number): Promise<number> {
    const station = await this.getStation(stationId);
    if (!station) throw new Error("Station not found");

    const existingQueue = this.queue.get(stationId) || [];
    const existingPosition = existingQueue.findIndex(entry => entry.userId === userId);

    if (existingPosition !== -1) {
      return existingPosition + 1; // Return current position if already in queue
    }

    const queueEntry: StationQueue = {
      id: this.currentId++,
      stationId,
      userId,
      joinedAt: new Date(),
      position: existingQueue.length + 1,
    };

    this.queue.set(stationId, [...existingQueue, queueEntry]);
    return queueEntry.position;
  }

  async leaveQueue(stationId: number, userId: number): Promise<void> {
    const existingQueue = this.queue.get(stationId) || [];
    const updatedQueue = existingQueue.filter(entry => entry.userId !== userId);

    // Update positions for remaining entries
    updatedQueue.forEach((entry, index) => {
      entry.position = index + 1;
    });

    this.queue.set(stationId, updatedQueue);
  }

  async getQueuePosition(stationId: number, userId: number): Promise<number | null> {
    const existingQueue = this.queue.get(stationId) || [];
    const entry = existingQueue.find(entry => entry.userId === userId);
    return entry ? entry.position : null;
  }

  async getQueueLength(stationId: number): Promise<number> {
    const existingQueue = this.queue.get(stationId) || [];
    return existingQueue.length;
  }

  async checkQueueAndUpdateSession(stationId: number): Promise<void> {
    const station = await this.getStation(stationId);
    if (!station || station.status !== "available") return;

    const existingQueue = this.queue.get(stationId) || [];
    if (existingQueue.length === 0) return;

    const nextInQueue = existingQueue[0];
    await this.leaveQueue(stationId, nextInQueue.userId);
    await this.updateStationSession(stationId, nextInQueue.userId);
  }
}

export const storage = new MemStorage();