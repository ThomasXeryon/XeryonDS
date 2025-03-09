import { useState, useEffect, useRef, useCallback } from 'react';

export interface WebSocketMessage {
  type: string;
  command?: string;
  direction?: string;
  rpiId?: string | number;
  stationId?: number;
  value?: any;
  frame?: string;
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<boolean>(false);
  const [frame, setFrame] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    console.log("[WebSocket] Attempting connection to:", wsUrl);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log("[WebSocket] Connected successfully");
      setConnectionStatus(true);
    };

    socket.onclose = (event) => {
      console.log("[WebSocket] Connection closed:", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean
      });
      setConnectionStatus(false);
      setFrame(null); // Clear frame on disconnect
    };

    socket.onerror = (error) => {
      console.error("[WebSocket] Connection error:", error);
      setConnectionStatus(false);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'camera_frame') {
          console.log("[WebSocket] Received camera frame:", {
            type: data.type,
            rpiId: data.rpiId,
            frameSize: data.frame?.length || 0
          });
          setFrame(data.frame);
        } else {
          console.log("[WebSocket] Received message:", data);
        }
      } catch (err) {
        console.error("[WebSocket] Failed to parse message:", err);
      }
    };

    return () => {
      if (socketRef.current) {
        console.log("[WebSocket] Cleaning up connection");
        socketRef.current.close();
      }
    };
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (!message.rpiId) {
      console.error("[WebSocket] Cannot send message - rpiId is missing:", message);
      return;
    }

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      console.log("[WebSocket] Sending message:", {
        type: message.type,
        command: message.command,
        direction: message.direction,
        rpiId: message.rpiId
      });
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn("[WebSocket] Cannot send - connection not open. State:", socketRef.current?.readyState);
    }
  }, []);

  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage,
    frame
  };
}