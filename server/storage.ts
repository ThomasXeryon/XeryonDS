import type { SessionStore } from 'express-session';
import { users, type User, type InsertUser } from "@shared/schema";
import session from "express-session";
import createMemoryStore from "memorystore";
import fs from 'fs/promises';
import path from 'path';

const MemoryStore = createMemoryStore(session);

interface IStorage {
  getUser(id: number): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  getAllUsers(): Promise<User[]>;
  updateUserAdmin(id: number, isAdmin: boolean): Promise<User>;
  sessionStore: SessionStore;
}

export class FileStorage implements IStorage {
  private filePath: string;
  sessionStore: SessionStore;
  private users: User[] = [];
  private nextId = 1;

  constructor() {
    this.filePath = path.join(process.cwd(), 'data', 'users.json');
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
        const data = await fs.readFile(this.filePath, 'utf-8');
        const parsed = JSON.parse(data);
        this.users = parsed.users;
        this.nextId = parsed.nextId;
      } catch (error) {
        // File doesn't exist or is invalid, start fresh
        this.users = [];
        this.nextId = 1;
        await this.saveToFile();
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
}

export const storage = new FileStorage();