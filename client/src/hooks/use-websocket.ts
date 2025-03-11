import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'react-hot-toast';

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
    // Create WebSocket connection with new path
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/appws`; // Changed from '/ws' to '/appws'
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

      // Attempt to reconnect after a short delay
      setTimeout(() => {
        console.log("[WebSocket] Attempting to reconnect...");
        socketRef.current = new WebSocket(wsUrl);
      }, 1000);
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
        } else if (data.type === 'error') {
          console.error("[WebSocket] Server error:", data.message, data.details || {});
        } else if (data.type === 'rpi_response') {
          console.log("[WebSocket] RPi response:", {
            status: data.status,
            rpiId: data.rpi_id,
            message: data.message
          });
        } else {
          console.log("[WebSocket] Received message:", data);
        }
      } catch (err) {
        console.error("[WebSocket] Failed to parse message:", err);
      }
    };

    // Only clean up on component unmount
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
      // Convert rpiId to string for consistency
      const finalMessage = {
        ...message,
        rpiId: String(message.rpiId)
      };

      console.log("[WebSocket] Sending message:", {
        type: finalMessage.type,
        command: finalMessage.command,
        direction: finalMessage.direction,
        rpiId: finalMessage.rpiId
      });

      socketRef.current.send(JSON.stringify(finalMessage));
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