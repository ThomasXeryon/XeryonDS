import express, { type Request, Response, NextFunction } from "express";
import { registerRoutes } from "./routes";
import { setupVite, serveStatic, log } from "./vite";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import { hashPassword } from "@shared/auth-utils";

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: false }));

// Add logging middleware
app.use((req, res, next) => {
  const start = Date.now();
  const path = req.path;
  let capturedJsonResponse: Record<string, any> | undefined = undefined;

  const originalResJson = res.json;
  res.json = function (bodyJson, ...args) {
    capturedJsonResponse = bodyJson;
    return originalResJson.apply(res, [bodyJson, ...args]);
  };

  res.on("finish", () => {
    const duration = Date.now() - start;
    if (path.startsWith("/api")) {
      let logLine = `${req.method} ${path} ${res.statusCode} in ${duration}ms`;
      if (capturedJsonResponse) {
        logLine += ` :: ${JSON.stringify(capturedJsonResponse)}`;
      }
      log(logLine);
    }
  });
  next();
});

// Setup auth before routes
setupAuth(app);

(async () => {
  try {
    // Initialize admin user if it doesn't exist
    const admin = await storage.getUserByUsername("admin");
    if (!admin) {
      console.log("Creating admin user...");
      const hashedPassword = await hashPassword("adminpass");
      const user = await storage.createUser({
        username: "admin",
        password: hashedPassword,
      });
      await storage.updateUserAdmin(user.id, true);
      console.log("Admin user created successfully");
    }

    // Get HTTP server with WebSocket support
    const server = await registerRoutes(app);

    // Error handling middleware
    app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
      const status = err.status || err.statusCode || 500;
      const message = err.message || "Internal Server Error";
      console.error("Server error:", err);
      res.status(status).json({ message });
    });

    if (app.get("env") === "development") {
      await setupVite(app, server);
    } else {
      serveStatic(app);
    }

    // Listen on port 5000 with proper host binding
    const port = 5000; // Force port 5000 for consistency
    server.listen(port, "0.0.0.0", () => {
      console.log(`Server started on port ${port}`);
      console.log(`WebSocket server ready for connections at ws://0.0.0.0:${port}`);
      log(`Server listening on port ${port}`);
    });
  } catch (error) {
    console.error("Failed to start server:", error);
    process.exit(1);
  }
})();