import type { SessionStore } from 'express-session';
import { type User, type InsertUser, type Station } from "@shared/schema";
import session from "express-session";
import createMemoryStore from "memorystore";
import fs from 'fs/promises';
import path from 'path';

const MemoryStore = createMemoryStore(session);

interface IStorage {
  // User methods
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;
  updateUserAdmin(id: number, isAdmin: boolean): Promise<User>;

  // Station methods
  getStations(): Promise<Station[]>;
  updateStationStatus(id: number, status: "available" | "in_use", userId?: number): Promise<Station>;
  startSession(stationId: number, userId: number): Promise<Station>;
  endSession(stationId: number): Promise<Station>;

  sessionStore: SessionStore;
}

export class FileStorage implements IStorage {
  private filePath: string;
  private stationsPath: string;
  sessionStore: SessionStore;
  private users: User[] = [];
  private stations: Station[] = [];
  private nextId = 1;

  constructor() {
    this.filePath = path.join(process.cwd(), 'data', 'users.json');
    this.stationsPath = path.join(process.cwd(), 'data', 'stations.json');
    this.sessionStore = new MemoryStore({
      checkPeriod: 86400000 // 24h
    });
    this.initializeStorage();
  }

  private async initializeStorage() {
    try {
      // Create data directory if it doesn't exist
      await fs.mkdir(path.join(process.cwd(), 'data'), { recursive: true });

      try {
        const userData = await fs.readFile(this.filePath, 'utf-8');
        const parsed = JSON.parse(userData);
        this.users = parsed.users;
        this.nextId = parsed.nextId;
      } catch (error) {
        // File doesn't exist or is invalid, start fresh
        this.users = [];
        this.nextId = 1;
        await this.saveToFile();
      }

      try {
        const stationData = await fs.readFile(this.stationsPath, 'utf-8');
        this.stations = JSON.parse(stationData);
      } catch (error) {
        // Initialize with some demo stations if file doesn't exist
        this.stations = [
          { id: 1, name: "XYZ-40 Demo Station", status: "available" },
          { id: 2, name: "PQ-50 Test Station", status: "available" }
        ];
        await fs.writeFile(this.stationsPath, JSON.stringify(this.stations, null, 2));
      }
    } catch (error) {
      console.error('Error initializing storage:', error);
      throw error;
    }
  }

  private async saveToFile() {
    const data = JSON.stringify({
      users: this.users,
      nextId: this.nextId
    }, null, 2);
    await fs.writeFile(this.filePath, data, 'utf-8');
  }

  private async saveStations() {
    await fs.writeFile(this.stationsPath, JSON.stringify(this.stations, null, 2));
  }

  // User methods
  async getUser(id: number): Promise<User | undefined> {
    return this.users.find(u => u.id === id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return this.users.find(u => u.username === username);
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const user: User = {
      id: this.nextId++,
      ...insertUser,
      isAdmin: false
    };
    this.users.push(user);
    await this.saveToFile();
    return user;
  }

  async getAllUsers(): Promise<User[]> {
    return this.users;
  }

  async updateUserAdmin(id: number, isAdmin: boolean): Promise<User> {
    const user = await this.getUser(id);
    if (!user) {
      throw new Error('User not found');
    }
    user.isAdmin = isAdmin;
    await this.saveToFile();
    return user;
  }

  // Station methods
  async getStations(): Promise<Station[]> {
    return this.stations;
  }

  async updateStationStatus(id: number, status: "available" | "in_use", userId?: number): Promise<Station> {
    const station = this.stations.find(s => s.id === id);
    if (!station) {
      throw new Error('Station not found');
    }
    station.status = status;
    if (status === "in_use" && userId) {
      station.currentSession = {
        userId,
        startTime: new Date().toISOString()
      };
    } else if (status === "available") {
      delete station.currentSession;
    }
    await this.saveStations();
    return station;
  }

  async startSession(stationId: number, userId: number): Promise<Station> {
    return this.updateStationStatus(stationId, "in_use", userId);
  }

  async endSession(stationId: number): Promise<Station> {
    return this.updateStationStatus(stationId, "available");
  }
}

export const storage = new FileStorage();