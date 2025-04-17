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
  const imageRef = useRef<HTMLImageElement | null>(null);
  const frameNumberRef = useRef<number | null>(null);
  const frameStartTimeRef = useRef<number | null>(null);

  // Process new frames with request animation frame for smoothest possible rendering
  useEffect(() => {
    if (!frame) return;
    
    // Skip effect if canvas isn't ready
    if (!canvasRef.current) return;
    
    // Update timestamp of the latest frame we received
    lastFrameTime.current = Date.now();
    lastValidFrame.current = frame;
    setLoading(false);
    setIsReconnecting(false);
    
    // Process frame in a non-blocking way using requestAnimationFrame
    // This ensures the browser can optimize rendering and avoid jank
    const processFrame = () => {
      if (!canvasRef.current) return;
      
      // Create an image if we don't have one yet
      if (!imageRef.current) {
        imageRef.current = new Image();
        imageRef.current.onload = () => {
          renderFrame();
          frameStartTimeRef.current = null; // Clear timing marker after render
        };
        
        imageRef.current.onerror = (e) => {
          console.error("[CameraFeed] Error loading frame:", e);
          setLoading(true);
        };
      }
      
      // Track when we started loading this frame
      frameStartTimeRef.current = performance.now();
      
      // Set the image source to the new frame
      if (imageRef.current.src !== frame) {
        imageRef.current.src = frame;
      }
    };
    
    // Render the frame to canvas once it's loaded
    const renderFrame = () => {
      if (!canvasRef.current || !imageRef.current) return;
      
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      
      // Make sure canvas is the right size
      const containerWidth = canvas.clientWidth;
      const containerHeight = canvas.clientHeight;
      
      if (canvas.width !== containerWidth || canvas.height !== containerHeight) {
        canvas.width = containerWidth;
        canvas.height = containerHeight;
      }
      
      // Clear canvas before drawing new frame
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Calculate aspect ratio to maintain image proportions
      const imgWidth = imageRef.current.width;
      const imgHeight = imageRef.current.height;
      const imgAspect = imgWidth / imgHeight;
      const canvasAspect = canvas.width / canvas.height;
      
      // Size calculations to center and fit image properly
      let drawWidth, drawHeight, offsetX, offsetY;
      
      if (imgAspect > canvasAspect) {
        // Image is wider than canvas
        drawWidth = canvas.width;
        drawHeight = canvas.width / imgAspect;
        offsetX = 0;
        offsetY = (canvas.height - drawHeight) / 2;
      } else {
        // Image is taller than canvas
        drawHeight = canvas.height;
        drawWidth = canvas.height * imgAspect;
        offsetX = (canvas.width - drawWidth) / 2;
        offsetY = 0;
      }
      
      // Draw image to canvas
      ctx.drawImage(imageRef.current, offsetX, offsetY, drawWidth, drawHeight);
      
      // Draw frame number indicator if available
      if (frameNumberRef.current !== null) {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(10, canvas.height - 30, 200, 20);
        ctx.fillStyle = 'white';
        ctx.font = '12px monospace';
        
        // Calculate and display frame processing time
        const processingTime = frameStartTimeRef.current 
          ? (performance.now() - frameStartTimeRef.current).toFixed(1) 
          : 'N/A';
          
        ctx.fillText(`Frame #${frameNumberRef.current} | ${processingTime}ms`, 15, canvas.height - 15);
      }
      
      // Log render performance
      if (frameStartTimeRef.current) {
        const totalRenderTime = performance.now() - frameStartTimeRef.current;
        console.log(`[CameraFeed] Frame render time: ${totalRenderTime.toFixed(1)}ms`);
      }
    };
    
    // Process the frame using requestAnimationFrame
    requestAnimationFrame(processFrame);
    
  }, [frame]);

  // Extract frame number from WebSocket data for metrics
  useEffect(() => {
    if (frame && frame.includes('frameNumber')) {
      try {
        // Try to extract frame number from data URL
        const match = frame.match(/frameNumber=(\d+)/);
        if (match && match[1]) {
          frameNumberRef.current = parseInt(match[1], 10);
        }
      } catch (e) {
        console.error("Failed to extract frame number", e);
      }
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
          {/* Replace img with canvas for better performance */}
          <canvas
            ref={canvasRef}
            className="w-full h-full"
            style={{ objectFit: 'contain' }}
          />

          {/* Fallback image only used for first load or if canvas fails */}
          {!canvasRef.current && (
            <img
              src={isFrameRecent && frame ? frame : lastValidFrame.current!}
              alt="Camera Feed"
              className="w-full h-full object-contain absolute top-0 left-0 opacity-0"
              style={{ visibility: 'hidden' }}
              onError={(e) => {
                console.error("[CameraFeed] Error loading frame:", e);
                setLoading(true);
              }}
              onLoad={() => console.log("[CameraFeed] Frame loaded successfully for RPi:", rpiId)}
            />
          )}

          {/* Reconnecting overlay that shows in corner when connection is lost */}
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