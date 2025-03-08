const sendSocketMessage = useCallback(
    (message: WebSocketMessage) => {
      if (!message.rpiId) {
        console.error("Cannot send message: No RPi ID specified", message);
        return;
      }

      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log("Sending WebSocket message:", message);
        socket.send(JSON.stringify(message));
      } else {
        console.error("WebSocket not connected");
      }
    },
    [socket]
  );

const sendCommand = useCallback(
    (rpiId: string, command: string, direction?: string) => {
      const message: WebSocketMessage = {
        type: "command",
        command,
        direction,
        rpiId,
        stationId: Number(currentStationId)
      };
      sendSocketMessage(message);
    },
    [currentStationId, sendSocketMessage]
  );
import { useState, useEffect, useRef, useCallback } from 'react';

interface WebSocketConnection {
  connected: boolean;
  sendMessage: (message: any) => void;
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<boolean>(false);
  const socketRef = useRef<WebSocket | null>(null);
  
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;
    
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
    
    return () => {
      socket.close();
    };
  }, []);
  
  const sendMessage = useCallback((message: any) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, message not sent:', message);
    }
  }, []);
  
  return {
    socket: socketRef.current,
    connectionStatus,
    sendMessage,
  };
}
