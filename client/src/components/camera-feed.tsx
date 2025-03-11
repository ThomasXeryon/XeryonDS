import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame } = useWebSocket();

  useEffect(() => {
    if (frame) {
      setLoading(false); // Stop loading when frame arrives
    }
  }, [frame]);

  // Show reconnecting state when connection is lost
  useEffect(() => {
    if (!connectionStatus) {
      setLoading(true);
    }
  }, [connectionStatus]);

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
            {connectionStatus ? 'Waiting for camera feed...' : 'Reconnecting...'}
          </div>
        </>
      ) : frame ? (
        <img
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
