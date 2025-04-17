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
  const reconnectAttemptsRef = useRef<number>(0);
  const { toast } = useToast();

  // Function to create a WebSocket connection
  const createConnection = useCallback(() => {
    try {
      // Close any existing socket first
      if (wsRef.current) {
        if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
          try {
            wsRef.current.close();
          } catch (e) {
            console.error("[WebSocket] Error closing existing connection:", e);
          }
        }
      }
      
      // Create WebSocket connection with new path
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/appws`;
      console.log(`[WebSocket] Attempting connection to: ${wsUrl} (attempt ${reconnectAttemptsRef.current})`);
      
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;
      
      socket.onopen = () => {
        console.log("[WebSocket] Connected successfully");
        reconnectAttemptsRef.current = 0; // Reset counter on successful connection
        setState(prev => ({ ...prev, connectionStatus: true }));
        
        // Register for specific RPi's feed if an ID is provided
        if (rpiId) {
          try {
            socket.send(JSON.stringify({
              type: 'register',
              rpiId
            }));
            console.log(`[WebSocket] Registered for RPi ${rpiId}`);
          } catch (e) {
            console.error("[WebSocket] Failed to register:", e);
          }
        }
      };
      
      socket.onclose = (event) => {
        console.log("[WebSocket] Connection closed:", event);
        setState(prev => ({ ...prev, connectionStatus: false }));
        scheduleReconnect();
      };
      
      socket.onerror = (error) => {
        console.error("[WebSocket] Connection error:", error);
        setState(prev => ({ ...prev, connectionStatus: false }));
        // No need to call scheduleReconnect() here as onclose will be called
      };
      
      socket.onmessage = handleMessage;
      
      return socket;
    } catch (error) {
      console.error("[WebSocket] Error creating connection:", error);
      scheduleReconnect();
      return null;
    }
  }, [rpiId]);
  
  // Schedule a reconnection with exponential backoff
  const scheduleReconnect = useCallback(() => {
    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
    }
    
    reconnectAttemptsRef.current++;
    
    // Calculate delay with exponential backoff, capped at 10 seconds
    const delay = Math.min(
      Math.pow(1.5, Math.min(reconnectAttemptsRef.current, 8)) * 1000,
      10000
    );
    
    console.log(`[WebSocket] Will attempt to reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
    
    reconnectTimeoutRef.current = window.setTimeout(() => {
      console.log("[WebSocket] Attempting to reconnect...");
      createConnection();
    }, delay);
  }, [createConnection]);
  
  // Set up the WebSocket connection
  useEffect(() => {
    const socket = createConnection();
    
    // Set up a ping interval to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ 
            type: 'ping',
            timestamp: new Date().toISOString()
          }));
        } catch (e) {
          console.error("[WebSocket] Error sending ping:", e);
        }
      }
    }, 15000); // Send ping every 15 seconds
    
    // Cleanup function to close WebSocket when component unmounts
    return () => {
      console.log("[WebSocket] Cleaning up WebSocket connection");
      
      clearInterval(pingInterval);
      
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      if (frameTimeoutRef.current) {
        window.clearTimeout(frameTimeoutRef.current);
        frameTimeoutRef.current = null;
      }
      
      if (wsRef.current) {
        try {
          // Remove all handlers first to prevent unnecessary callbacks
          wsRef.current.onopen = null;
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.onmessage = null;
          
          if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
            wsRef.current.close();
          }
        } catch (e) {
          console.error("[WebSocket] Error during cleanup:", e);
        }
        wsRef.current = null;
      }
    };
  }, [createConnection, rpiId]);

  // Keep track of the latest frame number to ensure we only process the newest frames
  const latestFrameNumberRef = useRef<number>(0);
  // Store last frame processing time to measure performance
  const lastProcessTimeRef = useRef<number>(Date.now());

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      const now = performance.now(); // Use high-resolution timer

      // Track and handle camera frames with ultra-low latency approach
      if (data.type === 'camera_frame') {
        // Skip this frame if we're already processing a newer one
        if (data.frameNumber && data.frameNumber < latestFrameNumberRef.current) {
          console.log(`[WebSocket] Skipping outdated frame #${data.frameNumber} (current: #${latestFrameNumberRef.current})`);
          return;
        }

        // Update the latest frame number
        if (data.frameNumber) {
          latestFrameNumberRef.current = data.frameNumber;
        }

        // Calculate processing delay for monitoring
        const processingDelay = now - lastProcessTimeRef.current;
        lastProcessTimeRef.current = now;

        // Measure end-to-end latency if timestamp is available
        let latency = null;
        if (data.timestamp) {
          const frameTime = new Date(data.timestamp).getTime();
          latency = Date.now() - frameTime;
        }

        // Log detailed frame info with performance metrics
        console.log(
          `[WebSocket] Frame #${data.frameNumber || 'unknown'} | ` +
          `Size: ${data.frame?.length || 0} chars | ` +
          `Process delay: ${processingDelay.toFixed(1)}ms | ` + 
          `End-to-end latency: ${latency !== null ? latency + 'ms' : 'unknown'}`
        );

        // Use lightweight state update with only necessary changes
        // This is much faster than updating the entire state object
        setState(prev => ({
          ...prev,
          frame: data.frame,
          lastFrameTime: Date.now()
        }));

      } else if (data.type === 'rpi_connected') {
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