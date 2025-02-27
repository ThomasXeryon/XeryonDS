import { users, stations, type User, type InsertUser, type Station } from "@shared/schema";
import session from "express-session";
import createMemoryStore from "memorystore";

const MemoryStore = createMemoryStore(session);

export interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  
  getStations(): Promise<Station[]>;
  getStation(id: number): Promise<Station | undefined>;
  updateStationSession(id: number, userId: number | null): Promise<Station>;
  
  sessionStore: session.SessionStore;
}

export class MemStorage implements IStorage {
  private users: Map<number, User>;
  private stations: Map<number, Station>;
  currentId: number;
  sessionStore: session.SessionStore;

  constructor() {
    this.users = new Map();
    this.stations = new Map();
    this.currentId = 1;
    this.sessionStore = new MemoryStore({
      checkPeriod: 86400000,
    });

    // Initialize demo stations
    this.stations.set(1, {
      id: 1,
      name: "Demo Station 1",
      status: "available",
      currentUserId: null,
      sessionStart: null,
    });
    this.stations.set(2, {
      id: 2, 
      name: "Demo Station 2",
      status: "available",
      currentUserId: null,
      sessionStart: null,
    });
  }

  async getUser(id: number): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find(
      (user) => user.username === username,
    );
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const id = this.currentId++;
    const user: User = { ...insertUser, id };
    this.users.set(id, user);
    return user;
  }

  async getStations(): Promise<Station[]> {
    return Array.from(this.stations.values());
  }

  async getStation(id: number): Promise<Station | undefined> {
    return this.stations.get(id);
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
    return updatedStation;
  }
}

export const storage = new MemStorage();
