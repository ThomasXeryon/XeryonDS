import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Validate database URL and connection parameters
const validateDatabaseConfig = () => {
  const { DATABASE_URL } = process.env;

  if (!DATABASE_URL) {
    throw new Error("DATABASE_URL environment variable is required");
  }

  try {
    // Test if URL is valid without logging sensitive data
    const url = new URL(DATABASE_URL);
    console.log(`Connecting to database at ${url.host}...`);
    return DATABASE_URL;
  } catch (err) {
    throw new Error(`Invalid DATABASE_URL format: ${err.message}`);
  }
};

// Create pool with validated config
export const pool = new Pool({
  connectionString: validateDatabaseConfig(),
  ssl: {
    rejectUnauthorized: false // Required for Neon database
  },
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
  connectionTimeoutMillis: 5000, // 5 second timeout
});

// Handle pool errors to prevent crashes
pool.on('error', (err) => {
  console.error('Unexpected database pool error:', err.message);
  // Don't crash the server on connection errors
});

// Create drizzle database instance
export const db = drizzle(pool, { schema });

// Test connection and log status
pool.connect()
  .then(client => {
    console.log('Successfully connected to database');
    client.release();
  })
  .catch(err => {
    console.error('Failed to connect to database:', {
      message: err.message,
      code: err.code
    });
  });