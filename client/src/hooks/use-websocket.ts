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
    if (socketRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`; // Use dedicated /ws path for UI clients

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log('WebSocket connected to UI endpoint');
      setConnectionStatus(true);
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected, attempting reconnect...');
      setConnectionStatus(false);
      reconnectTimeoutRef.current = setTimeout(connect, 2000);
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      socket.close();
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

  return {
    socket: socketRef.current,
    connectionStatus
  };
}