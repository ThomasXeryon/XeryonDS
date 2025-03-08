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
    const wsUrl = `${protocol}//${host}`;

    console.log(`WebSocket connecting to ${wsUrl}`);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log(`WebSocket connected to ${wsUrl}`);
      setConnectionStatus(true);
    };

    socket.onclose = (event) => {
      console.log("WebSocket disconnected:", event.code, event.reason);
      setConnectionStatus(false);
      reconnectTimeoutRef.current = setTimeout(connect, 2000);
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      socket.close();
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'camera_frame') {
          console.log(`Received frame from RPi ${data.rpiId}, size: ${data.frame?.length || 0} bytes`);

          if (data.frame) {
            const frameUrl = `data:image/jpeg;base64,${data.frame}`;
            console.log('Generated frame URL:', frameUrl.substring(0, 100) + '...');
          }
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

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage: useCallback((message: WebSocketMessage) => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify(message));
      } else {
        console.warn("Cannot send - WebSocket not connected");
      }
    }, [])
  };
}