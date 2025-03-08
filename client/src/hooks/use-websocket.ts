import { useState, useEffect, useRef, useCallback } from 'react';

export interface WebSocketMessage {
  type: string;
  rpiId?: string | number;
  frame?: string;
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<boolean>(false);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();

  const connect = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Get the port from window location
    const port = window.location.port;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname;

    // Use port 5000 if no port is specified
    const wsUrl = `${protocol}//${host}${port ? `:${port}` : ':5000'}`;
    console.log("Attempting WebSocket connection to:", wsUrl);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log(`WebSocket connected to ${wsUrl}`);
      setConnectionStatus(true);
    };

    socket.onclose = (event) => {
      console.log("WebSocket disconnected:", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
        url: wsUrl
      });
      setConnectionStatus(false);

      // Try to reconnect after 2 seconds
      reconnectTimeoutRef.current = setTimeout(connect, 2000);
    };

    socket.onerror = (error) => {
      console.error("WebSocket connection error:", error);
      socket.close();
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'camera_frame') {
          console.log(`Received frame from RPi ${data.rpiId}, size: ${data.frame?.length || 0} bytes`);
        }
      } catch (err) {
        console.error("Failed to parse message:", err);
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn("Cannot send - WebSocket not connected");
    }
  }, []);

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage
  };
}