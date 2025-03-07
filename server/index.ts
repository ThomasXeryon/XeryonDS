import express, { type Request, Response, NextFunction } from "express";
import { registerRoutes } from "./routes";
import { setupVite, serveStatic, log } from "./vite";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import { hashPassword } from "@shared/auth-utils";

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: false }));

// Setup auth before routes
setupAuth(app);

// Initialize admin user
(async () => {
  try {
    console.log("Checking for admin user...");
    const admin = await storage.getUserByUsername("admin");
    if (!admin) {
      console.log("Creating admin user...");
      const hashedPassword = await hashPassword("adminpass");
      const user = await storage.createUser({
        username: "admin",
        password: hashedPassword,
      });

      // Update user to be admin after creation
      await storage.updateUserAdmin(user.id, true);
      console.log("Admin user created successfully");
    } else {
      console.log("Admin user already exists");
    }

    const server = await registerRoutes(app);

    if (app.get("env") === "development") {
      await setupVite(app, server);
    } else {
      serveStatic(app);
    }

    const port = 5000;
    server.listen(port, "0.0.0.0", () => {
      log(`Server running on port ${port}`);
    });

  } catch (error) {
    console.error("Startup error:", error);
    process.exit(1);
  }
})();