
import WebSocket from 'ws';

// Simple RPi client simulator to test WebSocket integration
export function startRPiClient(rpiId: string, serverUrl: string = 'ws://localhost:5000') {
  const ws = new WebSocket(`${serverUrl}/rpi/${rpiId}`);
  
  ws.on('open', () => {
    console.log(`RPi Client ${rpiId} connected to server`);
    
    // Send initial status message
    const initialStatus = {
      status: 'ready',
      message: 'RPi device online and ready to accept commands'
    };
    ws.send(JSON.stringify(initialStatus));
  });
  
  ws.on('message', (data) => {
    try {
      const message = JSON.parse(data.toString());
      console.log(`RPi ${rpiId} received command:`, message);
      
      // Simulate processing and respond with success
      setTimeout(() => {
        const response = {
          status: 'success',
          message: `Executed command: ${message.command || 'unknown'}`
        };
        ws.send(JSON.stringify(response));
      }, 500); // Simulate 500ms processing time
    } catch (err) {
      console.error(`Error processing message on RPi ${rpiId}:`, err);
      ws.send(JSON.stringify({
        status: 'error',
        message: 'Failed to process command'
      }));
    }
  });
  
  ws.on('close', () => {
    console.log(`RPi Client ${rpiId} disconnected`);
    // Try to reconnect after 5 seconds
    setTimeout(() => startRPiClient(rpiId, serverUrl), 5000);
  });
  
  ws.on('error', (error) => {
    console.error(`RPi WebSocket error: ${error}`);
    ws.close();
  });
  
  return ws;
}
import WebSocket from 'ws';
import { log } from './vite';

export function startRPiClient(rpiId: string, serverUrl: string) {
  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 10;
  const baseReconnectDelay = 1000;

  const connect = () => {
    // Close any existing connection
    if (ws) {
      ws.close();
    }

    log(`Connecting RPi ${rpiId} to ${serverUrl}...`, 'rpi-client');
    
    // Connect to the WebSocket server
    ws = new WebSocket(serverUrl);

    ws.on('open', () => {
      log(`RPi ${rpiId} connected to server`, 'rpi-client');
      reconnectAttempts = 0;
      
      // Register the RPi with the server
      ws?.send(JSON.stringify({
        type: 'register',
        rpiId: rpiId,
        status: 'online'
      }));

      // Send heartbeat every 5 seconds
      const heartbeatInterval = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'heartbeat',
            rpiId: rpiId,
            timestamp: Date.now()
          }));
        } else {
          clearInterval(heartbeatInterval);
        }
      }, 5000);
    });

    ws.on('message', (data) => {
      try {
        const message = JSON.parse(data.toString());
        log(`RPi ${rpiId} received: ${JSON.stringify(message)}`, 'rpi-client');
        
        // Handle various command types
        if (message.type === 'command') {
          // Simulate command response
          setTimeout(() => {
            ws?.send(JSON.stringify({
              type: 'commandResponse',
              rpiId: rpiId,
              commandId: message.commandId,
              status: 'success',
              data: { result: `Executed ${message.command}` }
            }));
          }, 500);
        }
      } catch (error) {
        log(`Error parsing message: ${error}`, 'rpi-client');
      }
    });

    ws.on('close', () => {
      log(`RPi ${rpiId} disconnected from server`, 'rpi-client');
      // Attempt to reconnect with exponential backoff
      if (reconnectAttempts < maxReconnectAttempts) {
        const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts);
        reconnectAttempts++;
        setTimeout(connect, delay);
        log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts})`, 'rpi-client');
      } else {
        log(`Max reconnect attempts reached for RPi ${rpiId}`, 'rpi-client');
      }
    });

    ws.on('error', (error) => {
      log(`WebSocket error for RPi ${rpiId}: ${error.message}`, 'rpi-client');
    });
  };

  // Initial connection
  connect();

  return {
    sendData: (data: any) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
        return true;
      }
      return false;
    },
    close: () => {
      if (ws) {
        ws.close();
        ws = null;
      }
    }
  };
}
