import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
  showDebugOverlay?: boolean;
}

export function CameraFeed({ rpiId, showDebugOverlay = true }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame, lastFrameMetadata } = useWebSocket(String(rpiId));
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lastFrameTime = useRef<number | null>(null);
  const lastValidFrame = useRef<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);
  
  // Reference to track if this component is mounted
  const isMounted = useRef(true);
  
  // Set up cleanup when unmounting
  useEffect(() => {
    return () => {
      isMounted.current = false;
    };
  }, []);

  // Canvas rendering function
  const renderFrameToCanvas = (frameData: string, metadata?: {
    frameNumber?: number;
    timestamp?: number | null;
    latency?: number | null;
  }) => {
    if (!canvasRef.current || !isMounted.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Create an image object
    const img = new Image();
    
    // Only render once the image is loaded
    img.onload = () => {
      if (!canvasRef.current || !isMounted.current) return;
      
      // Get current canvas dimensions
      const canvasWidth = canvas.width;
      const canvasHeight = canvas.height;
      
      // Clear canvas
      ctx.clearRect(0, 0, canvasWidth, canvasHeight);
      
      // Draw the image preserving aspect ratio
      const imgAspect = img.width / img.height;
      const canvasAspect = canvasWidth / canvasHeight;
      
      let drawWidth, drawHeight, offsetX = 0, offsetY = 0;
      
      if (imgAspect > canvasAspect) {
        // Image is wider than canvas
        drawWidth = canvasWidth;
        drawHeight = canvasWidth / imgAspect;
        offsetY = (canvasHeight - drawHeight) / 2;
      } else {
        // Image is taller than canvas
        drawHeight = canvasHeight;
        drawWidth = canvasHeight * imgAspect;
        offsetX = (canvasWidth - drawWidth) / 2;
      }
      
      // Draw image centered
      ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
      
      // Add debug overlay if enabled
      if (showDebugOverlay && metadata) {
        // Configure text style
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, canvasHeight - 50, canvasWidth, 50);
        
        // Frame number and latency display
        ctx.font = '14px monospace';
        ctx.fillStyle = 'white';
        ctx.textBaseline = 'top';
        
        const frameNumberText = `Frame #${metadata.frameNumber || 'N/A'}`;
        const latencyText = metadata.latency !== null 
          ? `Latency: ${metadata.latency}ms` 
          : 'No latency data';
        
        // Position text
        ctx.fillText(frameNumberText, 10, canvasHeight - 45);
        ctx.fillText(latencyText, canvasWidth - ctx.measureText(latencyText).width - 10, canvasHeight - 45);
        
        // Timestamp in smaller font
        ctx.font = '10px monospace';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        
        const timestampText = metadata.timestamp 
          ? new Date(metadata.timestamp).toISOString() 
          : 'No timestamp';
        
        ctx.fillText(timestampText, 10, canvasHeight - 25);
      }
    };
    
    // Handle any errors
    img.onerror = () => {
      console.error("[CameraFeed] Error loading frame");
      if (isMounted.current) {
        setLoading(true);
      }
    };
    
    // Set the image source with proper URL formatting
    const frameUrl = frameData.startsWith('data:image') 
      ? frameData 
      : `data:image/jpeg;base64,${frameData}`;
    
    img.src = frameUrl;
  };

  // Resize canvas to match container
  useEffect(() => {
    const resizeCanvas = () => {
      if (!canvasRef.current || !canvasRef.current.parentElement) return;
      
      const parent = canvasRef.current.parentElement;
      const { width, height } = parent.getBoundingClientRect();
      
      canvasRef.current.width = width;
      canvasRef.current.height = height;
      
      // Re-render the last valid frame after resize
      if (lastValidFrame.current) {
        renderFrameToCanvas(lastValidFrame.current, lastFrameMetadata);
      }
    };
    
    // Initial resize
    resizeCanvas();
    
    // Add resize listener
    window.addEventListener('resize', resizeCanvas);
    
    // Cleanup
    return () => {
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [lastFrameMetadata]);

  // Process new frames
  useEffect(() => {
    if (frame) {
      // Using direct reference update rather than state for best performance
      lastFrameTime.current = Date.now();
      lastValidFrame.current = frame; // Store the last valid frame
      
      // Render frame to canvas
      renderFrameToCanvas(frame, lastFrameMetadata);
      
      // Only update state if component is still mounted
      if (isMounted.current) {
        setLoading(false); // Stop loading when frame arrives
        setIsReconnecting(false);
      }
    } else if (lastFrameTime.current && (Date.now() - lastFrameTime.current > 10000)) {
      // Only reload if no frames for 10 seconds (increased from 5s to avoid unnecessary reloads)
      // and only if we're still mounted
      if (isMounted.current) {
        window.location.reload();
      }
    }
  }, [frame, lastFrameMetadata]);

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      if (isMounted.current) {
        setIsReconnecting(true);
      }
      
      // Force reconnection after 10 seconds of no connection
      const timeout = setTimeout(() => {
        if (isMounted.current) {
          window.location.reload();
        }
      }, 10000);
      
      return () => clearTimeout(timeout);
    }
  }, [connectionStatus]);

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
      ) : (
        <>
          <canvas
            ref={canvasRef}
            className="w-full h-full"
          />

          {/* Reconnecting overlay that shows in corner when connection is lost */}
          {showReconnectingOverlay && (
            <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-xs">
              Reconnecting camera...
            </div>
          )}
          
          {/* Only use this as a fallback if rendering to canvas fails */}
          {!canvasRef.current && lastValidFrame.current && (
            <div className="absolute inset-0 flex items-center justify-center text-white bg-zinc-800/80">
              <p className="text-xs sm:text-sm">Canvas rendering not supported</p>
            </div>
          )}
        </>
      )}
      
      {/* Status text when no feed is available */}
      {!loading && !lastValidFrame.current && (
        <div className="absolute inset-0 flex items-center justify-center text-white bg-zinc-800/80">
          <p className="text-xs sm:text-sm">{statusText || "No camera feed available"}</p>
        </div>
      )}
    </div>
  );
}