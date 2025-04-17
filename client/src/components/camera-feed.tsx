import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const { connectionStatus, frame } = useWebSocket(String(rpiId));
  const lastFrameTimeRef = useRef<number>(performance.now());
  const lastValidFrameRef = useRef<string | null>(null);
  const frameQueueRef = useRef<string[]>([]);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const animationFrameIdRef = useRef<number | null>(null);

  // Fast-path event listener for frames
  useEffect(() => {
    const handleNewFrame = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.rpiId === String(rpiId)) {
        // High-priority frame processing - immediately consume the new frame
        const newFrame = customEvent.detail.frame;
        frameQueueRef.current = [newFrame]; // Only keep most recent frame
        lastFrameTimeRef.current = performance.now();
        lastValidFrameRef.current = newFrame;
        setLoading(false);
        setIsReconnecting(false);
      }
    };

    // Listen for direct frame events
    window.addEventListener('new-camera-frame', handleNewFrame);

    return () => {
      window.removeEventListener('new-camera-frame', handleNewFrame);
    };
  }, [rpiId]);

  // Initialize image object for canvas rendering
  useEffect(() => {
    imageRef.current = new Image();
    imageRef.current.crossOrigin = 'anonymous';
    
    // Pre-create image to avoid creation overhead during render
    return () => {
      imageRef.current = null;
    };
  }, []);

  // Handle direct frame state updates
  useEffect(() => {
    if (frame) {
      // Traditional state-based frame handling (backup path)
      frameQueueRef.current = [frame]; // Replace any queued frames with latest
      lastFrameTimeRef.current = performance.now();
      lastValidFrameRef.current = frame;
      setLoading(false);
      setIsReconnecting(false);
    } else if (lastFrameTimeRef.current && (performance.now() - lastFrameTimeRef.current > 5000)) {
      // Force reconnection if no frames for 5 seconds
      window.location.reload();
    }
  }, [frame]);

  // Canvas-based render loop for zero-delay rendering
  const renderLoop = useCallback(() => {
    if (!canvasRef.current || !imageRef.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    if (!ctx) return;
    
    // Process any frames in queue (will be at most 1 with our approach)
    if (frameQueueRef.current.length > 0) {
      const nextFrame = frameQueueRef.current[0];
      frameQueueRef.current = []; // Clear queue
      
      // Set the src and wait for it to load
      imageRef.current.onload = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(imageRef.current!, 0, 0, canvas.width, canvas.height);
      };
      
      imageRef.current.src = nextFrame;
    } else if (lastValidFrameRef.current && imageRef.current.complete) {
      // If no new frames but we have a valid frame, ensure it's displayed
      if (imageRef.current.src !== lastValidFrameRef.current) {
        imageRef.current.src = lastValidFrameRef.current;
      }
    }
    
    // Continue animation loop with high priority
    animationFrameIdRef.current = requestAnimationFrame(renderLoop);
  }, []);

  // Start render loop
  useEffect(() => {
    animationFrameIdRef.current = requestAnimationFrame(renderLoop);
    
    return () => {
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
    };
  }, [renderLoop]);

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

  // Check if the frame is recent (within the last 5 seconds)
  const isFrameRecent = !!lastValidFrameRef.current && 
                      (performance.now() - lastFrameTimeRef.current < 5000);

  // Determine if we should show the reconnecting overlay
  const showReconnectingOverlay = !isFrameRecent && isReconnecting;

  // Create status text
  const getStatusText = () => {
    if (!connectionStatus && !lastValidFrameRef.current) return "Connecting to server...";
    if (!isFrameRecent && !lastValidFrameRef.current) return "Waiting for camera feed...";
    if (showReconnectingOverlay) return "Reconnecting to camera...";
    return null;
  };

  const statusText = getStatusText();

  return (
    <div className="relative w-full aspect-video sm:aspect-[16/9] rounded-md overflow-hidden bg-black">
      {loading && !lastValidFrameRef.current ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-xs sm:text-sm text-white/70">
            {statusText || 'Waiting for camera feed...'}
          </div>
        </>
      ) : (
        <>
          {/* Canvas-based rendering for zero delay */}
          <canvas 
            ref={canvasRef}
            className="w-full h-full object-contain"
            width={1280}
            height={720}
          />

          {/* Reconnecting overlay that shows in corner when connection is lost */}
          {showReconnectingOverlay && (
            <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-xs">
              Reconnecting camera...
            </div>
          )}
        </>
      )}
    </div>
  );
}