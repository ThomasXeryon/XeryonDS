import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

neonConfig.webSocketConstructor = ws;

function validateDatabaseUrl(url: string | undefined): string {
  if (!url) {
    throw new Error(
      "DATABASE_URL environment variable is not set. " +
      "Please add it to your deployment secrets in the Secrets tab."
    );
  }

  try {
    const parsedUrl = new URL(url);
    if (!parsedUrl.protocol.startsWith('postgresql')) {
      throw new Error('Database URL must start with postgresql:// or postgres://');
    }
    return url;
  } catch (error) {
    throw new Error(
      `Invalid DATABASE_URL format: ${error instanceof Error ? error.message : 'unknown error'}. ` +
      "The URL should look like: postgresql://username:password@host:port/database"
    );
  }
}

// Validate and get the database URL
const databaseUrl = validateDatabaseUrl(process.env.DATABASE_URL);

// Log a masked version of the URL for debugging
const maskedUrl = databaseUrl.replace(/\/\/[^@]+@/, "//****:****@");
console.log("Using database URL:", maskedUrl);

// Create the connection pool and database instance
export const pool = new Pool({ connectionString: databaseUrl });
export const db = drizzle(pool, { schema });