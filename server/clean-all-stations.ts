
import { db } from './db';
import { stations, sessionLogs } from '@shared/schema';

// This script will delete ALL stations from the database
async function cleanAllStations() {
  try {
    console.log('Starting full database cleanup...');
    
    // First get the count to report
    const allStations = await db.select().from(stations);
    console.log(`Found ${allStations.length} stations in database.`);
    
    // Delete all session logs first (foreign key constraint)
    console.log('Deleting all session logs...');
    await db.delete(sessionLogs);
    
    // Then delete all stations
    console.log('Deleting all stations...');
    await db.delete(stations);
    
    console.log('Database cleanup complete. All stations have been removed.');
  } catch (error) {
    console.error('Error during full database cleanup:', error);
  } finally {
    process.exit(0);
  }
}

// Run the cleanup
cleanAllStations();
