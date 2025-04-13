import pg from 'pg';
import fs from 'fs';

const { Pool } = pg;

// Use environment variables to construct the connection string
const DATABASE_URL = (process.env.DATABASE_URL && process.env.DATABASE_URL.startsWith('postgres://')) 
  ? process.env.DATABASE_URL 
  : `postgres://${process.env.PGUSER}:${process.env.PGPASSWORD}@${process.env.PGHOST}:${process.env.PGPORT || '5432'}/${process.env.PGDATABASE}`;

console.log('Using database connection URL (credentials hidden):', DATABASE_URL.replace(/\/\/.*?@/, '//****:****@'));

// Create a connection pool
const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false }
});

// SQL to create our new tables
const createTablesSQL = `
-- Position data
CREATE TABLE IF NOT EXISTS "position_data" (
  "id" SERIAL PRIMARY KEY,
  "session_log_id" INTEGER REFERENCES "session_logs"("id"),
  "position" DOUBLE PRECISION NOT NULL,
  "timestamp" TIMESTAMP NOT NULL DEFAULT NOW(),
  "command_type" TEXT,
  "command_direction" TEXT,
  "command_step_size" DOUBLE PRECISION,
  "command_step_unit" TEXT
);

-- Command logs
CREATE TABLE IF NOT EXISTS "command_logs" (
  "id" SERIAL PRIMARY KEY,
  "session_log_id" INTEGER REFERENCES "session_logs"("id"),
  "command" TEXT NOT NULL,
  "direction" TEXT,
  "step_size" DOUBLE PRECISION,
  "step_unit" TEXT,
  "parameters" JSONB,
  "timestamp" TIMESTAMP NOT NULL DEFAULT NOW()
);

-- System health
CREATE TABLE IF NOT EXISTS "system_health" (
  "id" SERIAL PRIMARY KEY,
  "station_id" INTEGER REFERENCES "stations"("id"),
  "status" TEXT NOT NULL,
  "connection_latency" DOUBLE PRECISION,
  "cpu_usage" DOUBLE PRECISION,
  "memory_usage" DOUBLE PRECISION,
  "uptime_seconds" INTEGER,
  "details" JSONB,
  "timestamp" TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Technical specifications
CREATE TABLE IF NOT EXISTS "technical_specs" (
  "id" SERIAL PRIMARY KEY,
  "station_id" INTEGER REFERENCES "stations"("id") UNIQUE,
  "actuator_model" TEXT,
  "motion_type" TEXT,
  "travel_range" DOUBLE PRECISION,
  "resolution" DOUBLE PRECISION,
  "max_speed" DOUBLE PRECISION,
  "axis_configuration" TEXT,
  "created_at" TIMESTAMP NOT NULL DEFAULT NOW(),
  "updated_at" TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS "idx_position_data_session_log_id" ON "position_data"("session_log_id");
CREATE INDEX IF NOT EXISTS "idx_position_data_timestamp" ON "position_data"("timestamp");
CREATE INDEX IF NOT EXISTS "idx_command_logs_session_log_id" ON "command_logs"("session_log_id");
CREATE INDEX IF NOT EXISTS "idx_command_logs_timestamp" ON "command_logs"("timestamp");
CREATE INDEX IF NOT EXISTS "idx_system_health_station_id" ON "system_health"("station_id");
CREATE INDEX IF NOT EXISTS "idx_system_health_timestamp" ON "system_health"("timestamp");
`;

async function createTables() {
  const client = await pool.connect();
  try {
    console.log('Connected to database');
    console.log('Creating tables...');
    
    await client.query(createTablesSQL);
    
    console.log('Tables created successfully');
    
    // Test the connection to make sure the tables were created
    const { rows } = await client.query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('position_data', 'command_logs', 'system_health', 'technical_specs')"
    );
    
    console.log('Confirmed tables exist:', rows.map(row => row.table_name));
    
    // Check existing tables to ensure other tables exist
    const existingTables = await client.query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    );
    
    console.log('All tables in database:');
    existingTables.rows.forEach(row => {
      console.log(`- ${row.table_name}`);
    });
    
  } catch (err) {
    console.error('Error creating tables:', err);
    throw err;
  } finally {
    client.release();
    await pool.end();
  }
}

createTables().catch(console.error);