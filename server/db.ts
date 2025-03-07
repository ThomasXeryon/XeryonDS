import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

neonConfig.webSocketConstructor = ws;

// Check for DATABASE_URL with more helpful error message
if (!process.env.DATABASE_URL) {
  console.error("DATABASE_URL environment variable is not set.");
  console.error("Please add it to your deployment secrets in the Secrets tab.");
  
  // Exit with informative message for deployment logs
  if (process.env.NODE_ENV === 'production') {
    throw new Error(
      "DATABASE_URL must be set in deployment secrets. Go to Secrets tab and add DATABASE_URL with your database connection string."
    );
  }
}

export const pool = new Pool({ 
  connectionString: process.env.DATABASE_URL 
});
export const db = drizzle(pool, { schema });