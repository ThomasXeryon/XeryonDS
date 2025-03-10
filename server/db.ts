import { Pool, neonConfig } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-serverless';
import ws from "ws";
import * as schema from "@shared/schema";

// Configure the WebSocket constructor for Neon
neonConfig.webSocketConstructor = ws;

// Validate and construct connection string
const constructConnectionString = () => {
  const { DATABASE_URL, PGHOST, PGUSER, PGPASSWORD, PGDATABASE, PGPORT } = process.env;

  console.log('Checking database configuration...');
  console.log('PGHOST:', PGHOST);
  console.log('PGDATABASE:', PGDATABASE);
  console.log('PGPORT:', PGPORT);
  // Don't log sensitive credentials

  // If DATABASE_URL is provided and properly formatted, use it
  if (DATABASE_URL && (DATABASE_URL.startsWith('postgres://') || DATABASE_URL.startsWith('postgresql://'))) {
    console.log('Using DATABASE_URL connection string');
    return DATABASE_URL;
  }

  // Construct from individual components
  if (!PGHOST || !PGUSER || !PGPASSWORD || !PGDATABASE) {
    throw new Error("Database configuration missing. Required: PGHOST, PGUSER, PGPASSWORD, PGDATABASE");
  }

  console.log('Constructing connection string from individual components');
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
  connectionTimeoutMillis: 10000, // 10 second timeout
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000 // Close idle clients after 30 seconds
});

// Handle pool errors to prevent crashes
pool.on('error', (err: Error) => {
  console.error('Unexpected database pool error:', err.message);
  // Don't crash the server on connection errors
});

// Connection validation and reconnection logic
async function validateConnection() {
  let client;
  try {
    client = await pool.connect();
    const result = await client.query('SELECT NOW()');
    console.log('Successfully connected to database at:', result.rows[0].now);
    return true;
  } catch (err) {
    console.error('Error connecting to database:', {
      error: err instanceof Error ? err.message : String(err),
      stack: err instanceof Error ? err.stack : undefined
    });
    return false;
  } finally {
    if (client) client.release();
  }
}

// Initial connection attempt
validateConnection().then((success) => {
  if (!success) {
    console.log('Initial database connection failed, will retry automatically...');
  }
});

// Set up periodic reconnection check (every 30 seconds)
setInterval(async () => {
  console.log('Validating database connection...');
  await validateConnection();
}, 30000);

// Create drizzle database instance
export const db = drizzle(pool, { schema });