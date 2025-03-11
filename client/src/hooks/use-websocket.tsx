import { useState, useEffect } from 'react';

interface RPiResponse {
  type: string;
  rpiId: string;
  frame?: string;
}

export function useWebSocket() {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState(false);
  const [rpis, setRpis] = useState<string[]>([]);
  const [frame, setFrame] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<RPiResponse | null>(null);
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8080'); // Replace with your WebSocket URL

    ws.onopen = () => {
      setConnectionStatus(true);
      console.log('[WebSocket] Connected');
    };

    ws.onmessage = (event) => {
      const data: RPiResponse = JSON.parse(event.data);
      setLastResponse(data);

      if (data.type === 'rpi_list') {
        setRpis(data.rpiId.split(','));
      } else if (data.type === 'camera_frame') {
        console.log('[WebSocket] Received camera frame:', {
          type: data.type,
          rpiId: data.rpiId,
          frameSize: data.frame?.length || 0,
        });
        setFrame(data.frame || null);
        setLastUpdateTime(Date.now()); // Update timestamp to trigger re-renders
      } else {
        console.log('[WebSocket] Received:', data);
      }
    };

    ws.onclose = () => {
      setConnectionStatus(false);
      console.log('[WebSocket] Closed');
    };

    ws.onerror = (error) => {
      console.error('[WebSocket] Error:', error);
    };

    setSocket(ws);

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  const sendCommand = (command: string) => {
    if (socket) {
      socket.send(command);
    }
  };

  return {
    socket,
    connectionStatus,
    rpis,
    frame,
    lastResponse,
    lastUpdateTime,
    sendCommand,
  };
}