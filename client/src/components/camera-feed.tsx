import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame } = useWebSocket(String(rpiId));
  const lastFrameTime = useRef<number | null>(null);
  const lastValidFrame = useRef<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameNumberRef = useRef<number | null>(null);
  const animationRef = useRef<number | null>(null);
  const newFrameAvailable = useRef<boolean>(false);
  
  // Store the image object as a ref to maintain it between renders
  const imageRef = useRef<HTMLImageElement | null>(null);
  if (imageRef.current === null) {
    // Only create the image once to avoid memory leaks
    imageRef.current = new Image();
    // Set to standard HD resolution
    imageRef.current.width = 1280;
    imageRef.current.height = 720;
  }

  // This effect handles receiving and storing new frames from the WebSocket
  useEffect(() => {
    // Skip if no frame is available
    if (!frame) return;
    
    // Update timestamp and store the latest frame
    lastFrameTime.current = Date.now();
    lastValidFrame.current = frame;
    setLoading(false);
    setIsReconnecting(false);
    
    // Extract frame number from the data URL if available
    if (frame.includes('frameNumber')) {
      try {
        const match = frame.match(/frameNumber=(\d+)/);
        if (match && match[1]) {
          frameNumberRef.current = parseInt(match[1], 10);
          console.log(`[CameraFeed] Received frame #${frameNumberRef.current}`);
        }
      } catch (e) {
        console.error("[CameraFeed] Failed to extract frame number", e);
      }
    }
    
    // Flag that a new frame is available for rendering
    newFrameAvailable.current = true;
    
  }, [frame]);

  // This effect handles canvas initialization and setup
  useEffect(() => {
    // Skip if canvas isn't available
    if (!canvasRef.current) return;
    
    const canvas = canvasRef.current;
    
    // Initialize the canvas to HD resolution
    canvas.width = 1280;
    canvas.height = 720;
    
    // Setup canvas context once
    const ctx = canvas.getContext('2d', { alpha: false });
    if (!ctx) {
      console.error("[CameraFeed] Could not get canvas context");
      return;
    }
    
    // Function to render a frame on the canvas
    const renderFrame = () => {
      // Only draw if we have a canvas, image, and new frame
      if (!canvasRef.current || !imageRef.current || !newFrameAvailable.current) {
        // If no new frame, schedule next animation
        animationRef.current = requestAnimationFrame(renderFrame);
        return;
      }
      
      const startTime = performance.now();
      
      // Reset the new frame flag
      newFrameAvailable.current = false;
      
      const img = imageRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d', { alpha: false });
      
      if (!ctx) return;
      
      // Draw the frame to canvas (don't clear first as we're drawing full frames)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      
      // Draw frame number if available
      if (frameNumberRef.current !== null) {
        // Add a semi-transparent background for the text
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(10, canvas.height - 30, 200, 20);
        
        // Draw the frame number text
        ctx.fillStyle = 'white';
        ctx.font = '12px monospace';
        
        const renderTime = performance.now() - startTime;
        ctx.fillText(
          `Frame #${frameNumberRef.current} | ${renderTime.toFixed(1)}ms`, 
          15, 
          canvas.height - 15
        );
      }
      
      // Schedule next animation
      animationRef.current = requestAnimationFrame(renderFrame);
    };
    
    // Start the animation loop
    animationRef.current = requestAnimationFrame(renderFrame);
    
    // Cleanup function
    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, []);
  
  // Effect to handle image loading when the frame source changes
  useEffect(() => {
    // Skip if no frame or no image ref
    if (!frame || !imageRef.current) return;
    
    // Get the source of the current frame
    const currentSrc = imageRef.current.src;
    
    // Only set a new source if the frame has changed
    if (currentSrc !== frame) {
      // This is critical: create an onload handler BEFORE setting src
      const onLoadHandler = () => {
        // Mark that a new frame is ready to be drawn
        newFrameAvailable.current = true;
        
        // Log timing
        console.log(
          `[CameraFeed] Frame #${frameNumberRef.current || 'unknown'} loaded | ` + 
          `Size: ${frame.length} chars`
        );
        
        // Remove the handler after it's called
        if (imageRef.current) {
          imageRef.current.onload = null;
        }
      };
      
      const onErrorHandler = (e: Event) => {
        console.error("[CameraFeed] Error loading frame:", e);
        if (imageRef.current) {
          imageRef.current.onload = null;
          imageRef.current.onerror = null;
        }
      };
      
      // Set handlers
      imageRef.current.onload = onLoadHandler;
      imageRef.current.onerror = onErrorHandler;
      
      // Now set the source to trigger loading
      imageRef.current.src = frame;
    }
  }, [frame]);

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      setIsReconnecting(true);
      // Force reconnection after 5 seconds of no connection
      const timeout = setTimeout(() => {
        window.location.reload();
      }, 5000);
      return () => clearTimeout(timeout);
    }
  }, [connectionStatus]);

  // Handle automatic reconnection for stale frames
  useEffect(() => {
    const interval = setInterval(() => {
      if (lastFrameTime.current && (Date.now() - lastFrameTime.current > 5000)) {
        // Force reconnection if no frames for 5 seconds
        console.log("[CameraFeed] No frames for 5 seconds, reloading...");
        window.location.reload();
      }
    }, 1000);
    
    return () => clearInterval(interval);
  }, []);

  // Check if the frame is recent (within the last 5 seconds)
  const isFrameRecent = frame && lastFrameTime.current && (Date.now() - lastFrameTime.current < 5000);

  // Determine if we should show the reconnecting overlay
  const showReconnectingOverlay = !isFrameRecent && isReconnecting;

  // Create status text
  const getStatusText = () => {
    if (!connectionStatus && !lastValidFrame.current) return "Connecting to server...";
    if (!isFrameRecent && !frame && !lastValidFrame.current) return "Waiting for camera feed...";
    if (showReconnectingOverlay) return "Reconnecting to camera...";
    return null;
  };

  const statusText = getStatusText();

  return (
    <div className="relative w-full aspect-video sm:aspect-[16/9] rounded-md overflow-hidden bg-black">
      {loading && !lastValidFrame.current ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-xs sm:text-sm text-white/70">
            {statusText || 'Waiting for camera feed...'}
          </div>
        </>
      ) : (isFrameRecent && frame) || lastValidFrame.current ? (
        <>
          {/* Canvas for ultra-low latency rendering */}
          <canvas
            ref={canvasRef}
            className="w-full h-full"
            width={1280}
            height={720}
            style={{ objectFit: 'contain' }}
          />

          {/* Fallback for first load (not visible) */}
          {!canvasRef.current && lastValidFrame.current && (
            <img
              src={lastValidFrame.current}
              alt="Camera Feed"
              className="w-full h-full object-contain opacity-0"
              style={{ visibility: 'hidden' }}
            />
          )}

          {/* Reconnecting overlay */}
          {showReconnectingOverlay && (
            <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-xs">
              Reconnecting camera...
            </div>
          )}
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-white bg-zinc-800/80">
          <p className="text-xs sm:text-sm">{statusText || "No camera feed available"}</p>
        </div>
      )}
    </div>
  );
}