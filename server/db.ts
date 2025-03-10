import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Get database configuration from environment variables
if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL environment variable is required");
}

console.log('Initializing database connection...');

// Create connection pool
export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false // Required for Neon database
  },
  connectionTimeoutMillis: 10000, // 10 second timeout
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000 // Close idle clients after 30 seconds
});

// Handle pool errors
pool.on('error', (err: Error) => {
  console.error('Unexpected database pool error:', err.message);
});

// Validate database connection
async function validateConnection() {
  let client;
  try {
    client = await pool.connect();
    const result = await client.query('SELECT NOW()');
    console.log('Successfully connected to database at:', result.rows[0].now);
    return true;
  } catch (err) {
    console.error('Database connection error:', {
      error: err instanceof Error ? err.message : String(err),
      stack: err instanceof Error ? err.stack : undefined
    });
    return false;
  } finally {
    if (client) client.release();
  }
}

// Initial connection validation
validateConnection().then((success) => {
  if (!success) {
    console.error('Initial database connection failed. Check your database endpoint status and configuration.');
  }
});

// Regular connection check
setInterval(async () => {
  console.log('Validating database connection...');
  await validateConnection();
}, 30000);

// Create and export drizzle instance
export const db = drizzle(pool, { schema });