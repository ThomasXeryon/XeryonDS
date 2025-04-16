import pkg from 'pg';
const { Pool } = pkg;
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function applyMigration() {
  try {
    // Read the SQL file
    const sqlFile = path.join(__dirname, 'migrations', '0000_add_email_and_is_guest', 'migration.sql');
    const sql = fs.readFileSync(sqlFile, 'utf8');

    // Connect to the database
    const pool = new Pool({
      connectionString: process.env.DATABASE_URL,
    });

    try {
      console.log('Applying migration...');
      await pool.query(sql);
      console.log('Migration applied successfully!');
    } catch (error) {
      console.error('Error applying migration:', error);
    } finally {
      await pool.end();
    }
  } catch (error) {
    console.error('Error reading migration file:', error);
  }
}

applyMigration();