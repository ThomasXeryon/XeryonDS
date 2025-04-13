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

// Create a new pool with proper error handling and automatic reconnection
export const pool = new Pool({ 
  connectionString: dbUrl,
  ssl: {
    rejectUnauthorized: false // Required for Neon database
  },
  connectionTimeoutMillis: 5000, // 5 second timeout
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000 // Close idle clients after 30 seconds
});

// Handle pool errors to prevent crashes
pool.on('error', (err: any) => {
  console.error('Unexpected database pool error:', err?.message);
  // Don't crash the server on connection errors
});

// Connection validation and reconnection logic
async function validateConnection() {
  let client;
  try {
    client = await pool.connect();
    console.log('Successfully connected to database');
    return true;
  } catch (err: any) {
    console.error('Error connecting to database:', {
      code: err?.code,
      message: err?.message,
      detail: err?.detail,
      hint: err?.hint
    });
    
    // Don't throw an error, but let the application continue
    console.log('Will retry connecting to database automatically...');
    return false;
  } finally {
    if (client) client.release();
  }
}

// Initial connection attempt
validateConnection();

// Set up periodic reconnection check (every 60 seconds)
setInterval(async () => {
  console.log('Validating database connection...');
  await validateConnection();
}, 60000);

// Create drizzle database instance
export const db = drizzle(pool, { schema });