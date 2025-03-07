import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

neonConfig.webSocketConstructor = ws;

// Get the database URL from environment variables
const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  throw new Error("DATABASE_URL environment variable is not set");
}

// Create the connection pool and database instance
export const pool = new Pool({ connectionString: databaseUrl });
export const db = drizzle(pool, { schema });

// Test the connection and log success/failure
console.log("Attempting to connect to database...");
pool.connect()
  .then(() => {
    console.log("Successfully connected to database");
    const maskedUrl = databaseUrl.replace(/\/\/[^@]+@/, "//****:****@");
    console.log("Using database URL:", maskedUrl);
  })
  .catch((error) => {
    console.error("Failed to connect to database:", error);
    throw error; // Let the error propagate to the global handler
  });