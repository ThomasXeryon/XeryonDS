import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Ensure DATABASE_URL is set
if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL must be set");
}

console.log('Connecting to database...');

// Create a new pool
export const pool = new Pool({ 
  connectionString: process.env.DATABASE_URL,
  ssl: true
});

// Test the connection
pool.connect()
  .then(() => console.log('Successfully connected to database'))
  .catch(err => console.error('Error connecting to database:', err));

// Create drizzle database instance
export const db = drizzle(pool, { schema });