import { users, stations, sessionLogs, type User, type InsertUser, type Station, type SessionLog } from "@shared/schema";
import session from "express-session";
import createMemoryStore from "memorystore";
import { hashPassword } from "@shared/auth-utils";

const MemoryStore = createMemoryStore(session);

export interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;

  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  createStation(name: string): Promise<Station>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  deleteStation(id: number): Promise<void>;

  getSessionLogs(): Promise<SessionLog[]>;
  createSessionLog(stationId: number, userId: number): Promise<SessionLog>;
  updateSessionLog(id: number, endTime: Date): Promise<SessionLog>;
  incrementCommandCount(sessionLogId: number): Promise<void>;

  sessionStore: session.SessionStore;
}

export class MemStorage implements IStorage {
  private users: Map<number, User>;
  private stations: Map<number, Station>;
  private sessionLogs: Map<number, SessionLog>;
  private currentId: number;
  sessionStore: session.SessionStore;

  constructor() {
    this.users = new Map();
    this.stations = new Map();
    this.sessionLogs = new Map();
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

  async createStation(name: string): Promise<Station> {
    const id = this.currentId++;
    const station: Station = {
      id,
      name,
      status: "available",
      currentUserId: null,
      sessionStart: null,
      isActive: true,
    };
    this.stations.set(id, station);
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
}

export const storage = new MemStorage();