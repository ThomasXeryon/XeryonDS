import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
  stationId?: number;
}

export function CameraFeed({ rpiId, stationId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame, lastUpdateTime, lastFrameTime } = useWebSocket();
  const [key, setKey] = useState(Date.now()); // Add a key to force re-render
  const [isFrameRecent, setIsFrameRecent] = useState(false);

  // Force re-render on frame updates
  useEffect(() => {
    if (frame) {
      setLoading(false); // Stop loading when frame arrives
      setKey(Date.now()); // Update key to force re-render
    }
  }, [frame, lastUpdateTime]);

  // Check if we've received a frame in the last 2 seconds
  useEffect(() => {
    const checkFrameRecency = () => {
      const now = Date.now();
      const isRecent = lastFrameTime > 0 && now - lastFrameTime < 2000;
      setIsFrameRecent(isRecent);
    };

    // Initial check
    checkFrameRecency();
    
    // Set up interval to continuously check
    const interval = setInterval(checkFrameRecency, 500);
    
    return () => clearInterval(interval);
  }, [lastFrameTime]);

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      setLoading(true);
      setIsFrameRecent(false);
    }
  }, [connectionStatus]);

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading || !isFrameRecent ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
            Waiting for camera feed...
          </div>
        </>
      ) : frame ? (
        <img
          key={key} // Use key to force re-render when frame updates
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          onError={(e) => {
            console.error("[CameraFeed] Error loading frame:", e);
            setLoading(true);
          }}
          onLoad={() => console.log("[CameraFeed] Frame loaded successfully for RPi:", rpiId)}
        />
      ) : (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">No camera feed available</p>
        </div>
      )}
    </div>
  );
}