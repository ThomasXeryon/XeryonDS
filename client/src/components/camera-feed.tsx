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
  const frameNumberRef = useRef<number | null>(null);
  const frameInfoRef = useRef<HTMLDivElement | null>(null);
  
  // Store the frame size for statistics display
  const [frameSize, setFrameSize] = useState<number>(0);
  
  // Effect to process and record new frames when they arrive
  useEffect(() => {
    if (!frame) return;
    
    const now = Date.now();
    
    // Update timestamps and loading states
    lastFrameTime.current = now;
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
    
    // Calculate and store frame size
    setFrameSize(frame.length);
    
    // Update frame info overlay
    updateFrameInfo(frameNumberRef.current, frame.length);
  }, [frame]);
  
  // Update frame information overlay
  const updateFrameInfo = (frameNum: number | null, size: number) => {
    if (!frameInfoRef.current) return;
    
    const infoElement = frameInfoRef.current;
    infoElement.textContent = `Frame #${frameNum || 'unknown'} | ${(size / 1024).toFixed(1)} KB`;
  };

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      setIsReconnecting(true);
      // Force reconnection after 5 seconds of no connection
      const timeout = setTimeout(() => {
        console.log("[CameraFeed] WebSocket connection lost, reloading...");
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
  
  // Get current frame to display (the latest frame or last valid frame)
  const currentFrame = isFrameRecent && frame ? frame : lastValidFrame.current;

  return (
    <div className="relative w-full aspect-video sm:aspect-[16/9] rounded-md overflow-hidden bg-black">
      {loading && !lastValidFrame.current ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-xs sm:text-sm text-white/70">
            {statusText || 'Waiting for camera feed...'}
          </div>
        </>
      ) : currentFrame ? (
        <>
          {/* Simple img element for reliable rendering */}
          <img
            src={currentFrame}
            alt="Camera Feed"
            className="w-full h-full object-contain"
            style={{ imageRendering: 'optimizeSpeed' }}
            onError={(e) => {
              console.error("[CameraFeed] Error loading frame:", e);
              setLoading(true);
            }}
          />

          {/* Frame info overlay */}
          <div 
            ref={frameInfoRef}
            className="absolute bottom-2 left-2 bg-black/60 text-white px-2 py-1 rounded text-xs font-mono"
          >
            {frameNumberRef.current !== null ? 
              `Frame #${frameNumberRef.current} | ${(frameSize / 1024).toFixed(1)} KB` : 
              'Waiting for frame data...'}
          </div>

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