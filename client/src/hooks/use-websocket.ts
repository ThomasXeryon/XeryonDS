
import { useState, useEffect, useRef, useCallback } from 'react';

export interface WebSocketMessage {
  type: string;
  command?: string;
  direction?: string;
  rpiId?: string | number;
  stationId?: number;
  value?: any;
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<boolean>(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Create WebSocket connection
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    console.log("Connecting to WebSocket at:", wsUrl);
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    // Set up event handlers
    socket.onopen = () => {
      console.log('WebSocket connected');
      setConnectionStatus(true);
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected');
      setConnectionStatus(false);
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionStatus(false);
    };

    // Clean up on unmount
    return () => {
      console.log("Closing WebSocket connection");
      socket.close();
    };
  }, []);

  // Function to send messages through the WebSocket
  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      console.log("Sending WebSocket message:", message);
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, []);

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage
  };
}
