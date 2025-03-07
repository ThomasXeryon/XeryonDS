import type { Express } from "express";
import { createServer, type Server } from "http";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import express from "express";
import multer from "multer";
import path from "path";
import fs from "fs/promises";

function isAdmin(req: Express.Request) {
  return req.isAuthenticated() && req.user?.isAdmin;
}

export async function registerRoutes(app: Express): Promise<Server> {
  setupAuth(app);

  const httpServer = createServer(app);

  // Admin routes
  app.get("/api/admin/users", async (req, res) => {
    if (!isAdmin(req)) return res.sendStatus(403);
    const users = await storage.getAllUsers();
    res.json(users);
  });

  return httpServer;
}