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
    console.log('[WebSocket] Connecting to:', wsUrl);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log('[WebSocket] Connected');
      setConnectionStatus(true);
    };

    socket.onclose = (event) => {
      console.log('[WebSocket] Disconnected:', event.code, event.reason);
      setConnectionStatus(false);
    };

    socket.onerror = (error) => {
      console.error('[WebSocket] Error:', error);
      setConnectionStatus(false);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[WebSocket] Received:', data);
      } catch (err) {
        console.error('[WebSocket] Failed to parse message:', err);
      }
    };

    return () => {
      if (socketRef.current) {
        console.log('[WebSocket] Cleaning up connection');
        socketRef.current.close();
      }
    };
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Sending:', message);
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[WebSocket] Cannot send - not connected:', message);
    }
  }, []);

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage
  };
}