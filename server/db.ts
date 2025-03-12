import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Validate database URL
if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL environment variable is required");
}

// Create a new pool with proper configuration
export const pool = new Pool({ 
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false // Required for Neon database
  },
  connectionTimeoutMillis: 5000, // 5 second timeout
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
});

// Handle pool errors to prevent crashes
pool.on('error', (err) => {
  console.error('Unexpected database pool error:', err.message);
  // Don't crash the server on connection errors
});

// Create drizzle database instance
export const db = drizzle(pool, { schema });