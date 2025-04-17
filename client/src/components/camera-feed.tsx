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
  const imgRef = useRef<HTMLImageElement>(null);
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

  useEffect(() => {
    if (frame) {
      // Using direct reference update rather than state for best performance
      lastFrameTime.current = Date.now();
      lastValidFrame.current = frame; // Store the last valid frame
      
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
  }, [frame]);

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      if (isMounted.current) {
        setIsReconnecting(true);
      }
      
      // Force reconnection after 10 seconds of no connection (increased from 5s)
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
      ) : (isFrameRecent && frame) || lastValidFrame.current ? (
        <>
          <img
            ref={imgRef}
            src={isFrameRecent && frame ? frame : lastValidFrame.current!}
            alt="Camera Feed"
            className="w-full h-full object-contain"
            onError={(e) => {
              console.error("[CameraFeed] Error loading frame:", e);
              setLoading(true);
            }}
            // Removed onLoad console log to reduce overhead
          />

          {/* Reconnecting overlay that shows in corner when connection is lost */}
          {showReconnectingOverlay && (
            <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-xs">
              Reconnecting camera...
            </div>
          )}
          
          {/* Debug overlay with frame information */}
          {showDebugOverlay && lastFrameMetadata && (
            <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-white p-1 text-xs font-mono">
              <div className="flex justify-between">
                <span>Frame #{lastFrameMetadata.frameNumber || 'N/A'}</span>
                <span>
                  {lastFrameMetadata.latency !== null 
                    ? `Latency: ${lastFrameMetadata.latency}ms` 
                    : 'No latency data'}
                </span>
              </div>
              <div className="text-[8px] opacity-70">
                {lastFrameMetadata.timestamp 
                  ? new Date(lastFrameMetadata.timestamp).toISOString() 
                  : 'No timestamp'}
              </div>
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