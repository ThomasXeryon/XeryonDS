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

  // Keep track of the latest frame and its metadata to ensure zero-latency display
  const frameBufferRef = useRef<{timestamp: number, frame: string, frameNumber: number, positionText?: string}[]>([]);
  const maxBufferLength = 3; // Only keep the latest 3 frames to avoid memory issues
  const lastDisplayedFrameNumber = useRef<number>(0);
  const lastProcessTimeRef = useRef<number>(Date.now());
  
  // Function to process the frame buffer and get the latest frame
  const processFrameBuffer = useCallback(() => {
    if (frameBufferRef.current.length === 0) return;
    
    // Sort buffer by frameNumber (descending)
    frameBufferRef.current.sort((a, b) => b.frameNumber - a.frameNumber);
    
    // Get the latest frame
    const latestFrame = frameBufferRef.current[0];
    
    // If this is a new frame we haven't shown yet
    if (latestFrame.frameNumber > lastDisplayedFrameNumber.current) {
      // Update the frame in state
      setState(prev => ({
        ...prev,
        frame: latestFrame.frame,
        lastFrameTime: Date.now()
      }));
      
      // Update our tracking
      lastDisplayedFrameNumber.current = latestFrame.frameNumber;
      
      // Log performance metrics
      const now = Date.now();
      const endToEndLatency = now - latestFrame.timestamp;
      console.log(
        `[WebSocket] Displaying frame #${latestFrame.frameNumber} | ` +
        `End-to-end latency: ${endToEndLatency}ms | ` +
        `Buffer size: ${frameBufferRef.current.length} frames`
      );
    }
    
    // Trim buffer to keep only recent frames
    if (frameBufferRef.current.length > maxBufferLength) {
      frameBufferRef.current = frameBufferRef.current.slice(0, maxBufferLength);
    }
  }, []);

  // Set up a continuous RAF loop to always show the latest frame
  useEffect(() => {
    let rafId: number;
    
    const updateLoop = () => {
      processFrameBuffer();
      rafId = requestAnimationFrame(updateLoop);
    };
    
    // Start the loop
    rafId = requestAnimationFrame(updateLoop);
    
    // Clean up
    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [processFrameBuffer]);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      const now = performance.now(); // Use high-resolution timer

      // Track and handle camera frames with ultra-low latency approach
      if (data.type === 'camera_frame') {
        // Extract metadata
        const frameNumber = data.frameNumber || 0;
        const timestamp = data.timestamp ? new Date(data.timestamp).getTime() : Date.now();
        const positionText = data.positionText || '';
        
        // Store frame in buffer - we'll process it in our RAF loop
        frameBufferRef.current.push({
          frame: data.frame,
          frameNumber,
          timestamp,
          positionText
        });
        
        // Calculate processing delay for monitoring
        const processingDelay = now - lastProcessTimeRef.current;
        lastProcessTimeRef.current = now;
        
        // Immediately update the frame to avoid waiting for the next RAF cycle
        // This ensures we get the frame on screen as fast as possible
        setState(prev => ({
          ...prev,
          frame: data.frame,
          lastFrameTime: Date.now()
        }));
        
        // Log receipt of frame
        console.log(
          `[WebSocket] Received frame #${frameNumber} | ` +
          `Position: ${positionText} | ` +
          `Size: ${data.frame?.length || 0} chars | ` +
          `Process delay: ${processingDelay.toFixed(1)}ms`
        );

      } else if (data.type === 'position_update') {
        // Update the current position state
        setState(prev => ({
          ...prev,
          lastResponse: data
        }));
        
        // Extract position and timestamp
        const position = data.epos;
        const timestamp = data.timestamp ? new Date(data.timestamp).getTime() : Date.now();
        
        // Log position update
        console.log(`[WebSocket] Position update: ${position} mm at ${new Date(timestamp).toISOString()}`);
        
        // Create and dispatch a custom event for the position graph
        const positionEvent = new CustomEvent('position-update', {
          detail: {
            position,
            timestamp,
            rpiId: data.rpiId
          }
        });
        window.dispatchEvent(positionEvent);
        
      } else if (data.type === 'custom_event') {
        // Forward custom events from the server to the frontend
        if (data.eventName === 'position-update') {
          const positionEvent = new CustomEvent(data.eventName, {
            detail: data.data
          });
          window.dispatchEvent(positionEvent);
        }
        
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