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
    // Create WebSocket connection with detailed logging
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log('\n=== WebSocket Connection Debug ===');
    console.log('Window Location:', {
      protocol: window.location.protocol,
      host: window.location.host,
      pathname: window.location.pathname
    });
    console.log('Computed WebSocket URL:', wsUrl);
    console.log('==============================\n');

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    const setupEventHandlers = (ws: WebSocket) => {
      ws.onopen = () => {
        console.log('[WebSocket] Connected successfully');
        setConnectionStatus(true);
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean
        });
        setConnectionStatus(false);
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Connection error:', error);
        setConnectionStatus(false);
      };

      // Add message logging
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[WebSocket] Received message:', data);
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err);
        }
      };
    };

    setupEventHandlers(socket);

    // Implement reconnection logic
    let reconnectAttempt = 0;
    const maxReconnectAttempts = 5;
    let reconnectTimeout: NodeJS.Timeout;

    const reconnect = () => {
      if (reconnectAttempt >= maxReconnectAttempts) {
        console.log('[WebSocket] Max reconnection attempts reached');
        return;
      }

      if (socketRef.current?.readyState === WebSocket.CLOSED) {
        reconnectAttempt++;
        console.log(`[WebSocket] Attempting to reconnect (${reconnectAttempt}/${maxReconnectAttempts})...`);
        socketRef.current = new WebSocket(wsUrl);
        setupEventHandlers(socketRef.current);
      }
    };

    // Clean up on unmount
    return () => {
      clearTimeout(reconnectTimeout);
      if (socketRef.current) {
        console.log("[WebSocket] Closing connection");
        socketRef.current.close();
      }
    };
  }, []);

  // Function to send messages through the WebSocket
  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Sending message:', message);
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('[WebSocket] Cannot send message - connection not open:', message);
    }
  }, []);

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage
  };
}