
import { exec } from 'child_process';
import path from 'path';

// Get the RPi ID from command line arguments or use a default
const rpiId = process.argv[2] || 'RPI1';

console.log(`Starting RPi simulator with ID: ${rpiId}`);

// Get the path to the Python script - using combined version
const scriptPath = path.join(__dirname, 'combined-test-client.py');

// Execute the Python script with the RPi ID as an argument
const pythonProcess = exec(`python ${scriptPath} ${rpiId}`, (error, stdout, stderr) => {
  if (error) {
    console.error(`Error: ${error.message}`);
    return;
  }
  if (stderr) {
    console.error(`stderr: ${stderr}`);
    return;
  }
  console.log(`stdout: ${stdout}`);
});

// Forward stdout and stderr
pythonProcess.stdout?.on('data', (data) => {
  console.log(`${data}`);
});

pythonProcess.stderr?.on('data', (data) => {
  console.error(`${data}`);
});

// Keep the process running
process.on('SIGINT', () => {
  console.log('Shutting down RPi simulator');
  process.exit(0);
});
