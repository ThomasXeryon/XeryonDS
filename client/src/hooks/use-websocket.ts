import { useState, useEffect, useCallback, useRef } from 'react';
import { useToast } from "./use-toast";

// Define the structure for WebSocket hook data
interface WebSocketState {
  connectionStatus: boolean;
  frame: string | null;
  rpiStatus: Record<string, boolean>;
  lastResponse: any;
  lastFrameTime: number | null;
}

export function useWebSocket(rpiId?: string) {
  const [state, setState] = useState<WebSocketState>({
    connectionStatus: false,
    frame: null,
    rpiStatus: {},
    lastResponse: null,
    lastFrameTime: null
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const frameTimeoutRef = useRef<number | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    // Create WebSocket connection with new path
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/appws`; // Changed from '/ws' to '/appws'
    console.log("[WebSocket] Attempting connection to:", wsUrl);

    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      console.log("[WebSocket] Connected successfully");
      setState(prev => ({ ...prev, connectionStatus: true }));

      // Register for specific RPi's feed if an ID is provided
      if (rpiId) {
        socket.send(JSON.stringify({
          type: 'register',
          rpiId
        }));
        console.log(`[WebSocket] Registered for RPi ${rpiId}`);
      }
    };

    socket.onclose = (event) => {
      console.log("[WebSocket] Connection closed:", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean
      });
      setState(prev => ({ ...prev, connectionStatus: false }));

      // Set a flag to show reconnecting status after a short delay
      const reconnectStatusTimeout = window.setTimeout(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          console.log("[WebSocket] Setting reconnecting status");
          setState(prev => ({ ...prev, connectionStatus: false, frame: null }));
        }
      }, 5000);

      // Implement exponential backoff for reconnection attempts
      const backoffTime = Math.min(1000 * (Math.pow(2, Math.floor(Math.random() * 4))), 10000);
      console.log(`[WebSocket] Will attempt to reconnect in ${backoffTime}ms`);

      // Attempt to reconnect with exponential backoff
      reconnectTimeoutRef.current = window.setTimeout(() => {
        console.log("[WebSocket] Attempting to reconnect...");
        try {
          const newSocket = new WebSocket(wsUrl);
          wsRef.current = newSocket;

          // Set up event handlers for the new socket
          newSocket.onopen = socket.onopen;
          newSocket.onmessage = socket.onmessage;
          newSocket.onerror = socket.onerror;
          newSocket.onclose = socket.onclose;
        } catch (error) {
          console.error("[WebSocket] Failed to create new connection:", error);
        }

        // Clear the reconnect status timeout
        window.clearTimeout(reconnectStatusTimeout);
      }, backoffTime);
    };

    socket.onerror = (error) => {
      console.error("[WebSocket] Connection error:", error);
      setState(prev => ({ ...prev, connectionStatus: false }));
    };

    socket.onmessage = handleMessage;

    // Cleanup function to close WebSocket when component unmounts
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (frameTimeoutRef.current) {
        window.clearTimeout(frameTimeoutRef.current);
        frameTimeoutRef.current = null;
      }
    };
  }, [rpiId]); // Added rpiId to dependencies

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      // Fast-path optimization for camera frames
      // Check if this is likely a camera frame without fully parsing the JSON first
      if (event.data.indexOf('"type":"camera_frame"') !== -1) {
        try {
          // Parse the data for camera frames
          const data = JSON.parse(event.data);
          
          if (data.type === 'camera_frame') {
            // Process frame with highest possible priority
            const frameData = data.frame.startsWith('data:') ? 
                             data.frame : 
                             `data:image/jpeg;base64,${data.frame}`;
                        
            // ZERO BACKLOG OPTIMIZATION:
            // Dispatch custom event for ultra-high-priority processing
            // This bypasses React's rendering cycle entirely
            window.dispatchEvent(new CustomEvent('new-camera-frame', { 
              detail: { 
                rpiId: data.rpiId,
                frame: frameData,
                timestamp: data.timestamp,
                frameNumber: data.frameNumber
              }
            }));
            
            // Also update React state as a backup path
            setState(prev => ({
              ...prev,
              frame: frameData,
              lastFrameTime: performance.now() // Use high-precision timing
            }));
            
            // Skip further processing for maximum speed
            return;
          }
        } catch (e) {
          // If fast-path fails, continue with normal processing
          console.error('Fast-path camera frame processing failed:', e);
        }
      }

      // Normal path for all other message types
      const data = JSON.parse(event.data);

      // Handle different message types
      if (data.type === 'rpi_connected') {
        setState(prev => ({
          ...prev,
          rpiStatus: {
            ...prev.rpiStatus,
            [data.rpiId]: true
          }
        }));
        toast({
          title: "Device Connected",
          description: `RPi ${data.rpiId} is now connected`,
        });
      } else if (data.type === 'rpi_disconnected') {
        setState(prev => ({
          ...prev,
          rpiStatus: {
            ...prev.rpiStatus,
            [data.rpiId]: false
          },
          frame: null // Clear frame when RPi disconnects
        }));
        toast({
          title: "Device Disconnected",
          description: `RPi ${data.rpiId} has disconnected`,
          variant: "destructive",
        });
      } else if (data.type === 'camera_frame') {
        // This is the backup path for camera frames 
        // Our fast path should handle most camera frames
        const frameData = data.frame.startsWith('data:') ? 
                         data.frame : 
                         `data:image/jpeg;base64,${data.frame}`;
        
        setState(prev => ({
          ...prev,
          frame: frameData,
          lastFrameTime: performance.now()
        }));
      } else {
        // Store all other responses in lastResponse
        setState(prev => ({
          ...prev,
          lastResponse: data
        }));
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  }, [toast]);

  const sendMessage = useCallback((message: any) => {
    if (!message.rpiId) {
      console.error("[WebSocket] Cannot send message - rpiId is missing:", message);
      return;
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
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

      wsRef.current.send(JSON.stringify(finalMessage));
    } else {
      console.warn("[WebSocket] Cannot send - connection not open. State:", wsRef.current?.readyState);
    }
  }, []);

  return {
    socket: wsRef.current,
    connectionStatus: state.connectionStatus,
    sendMessage,
    frame: state.frame,
    rpiStatus: state.rpiStatus,
    lastResponse: state.lastResponse
  };
}