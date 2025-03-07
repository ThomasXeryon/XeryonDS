import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Validate and construct connection string
const constructConnectionString = () => {
  const { DATABASE_URL, PGHOST, PGUSER, PGPASSWORD, PGDATABASE, PGPORT } = process.env;

  // If DATABASE_URL is provided and properly formatted, use it
  if (DATABASE_URL && (DATABASE_URL.startsWith('postgres://') || DATABASE_URL.startsWith('postgresql://'))) {
    return DATABASE_URL;
  }

  // Construct from individual components
  if (!PGHOST || !PGUSER || !PGPASSWORD || !PGDATABASE) {
    throw new Error("Database configuration missing. Required: PGHOST, PGUSER, PGPASSWORD, PGDATABASE");
  }

  return `postgres://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT || '5432'}/${PGDATABASE}`;
};

// Get database URL
const dbUrl = constructConnectionString();

// Log connection attempt (without credentials)
const logUrl = new URL(dbUrl);
console.log(`Connecting to database at ${logUrl.host}${logUrl.pathname}...`);

// Create a new pool with proper error handling
export const pool = new Pool({ 
  connectionString: dbUrl,
  ssl: {
    rejectUnauthorized: false // Required for Neon database
  },
  connectionTimeoutMillis: 5000, // 5 second timeout
  max: 20 // Maximum number of clients in the pool
});

// Test the connection with detailed error handling
pool.connect()
  .then(() => {
    console.log('Successfully connected to database');
  })
  .catch(err => {
    console.error('Error connecting to database:', {
      code: err.code,
      message: err.message,
      detail: err.detail,
      hint: err.hint,
      position: err.position,
      host: logUrl.host,
      database: logUrl.pathname.slice(1)
    });
    // Throw an error with deployment-friendly message
    throw new Error(`Failed to connect to database. Please ensure all database environment variables are properly configured in your deployment settings. Error: ${err.message}`);
  });

// Create drizzle database instance
export const db = drizzle(pool, { schema });