import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame, reconnect } = useWebSocket();
  const lastFrameTime = useRef<number | null>(null);

  useEffect(() => {
    if (frame) {
      lastFrameTime.current = Date.now();
      setLoading(false); // Stop loading when frame arrives
    }
  }, [frame]);

  // Show reconnecting state when connection is lost and attempt reconnection
  useEffect(() => {
    if (!connectionStatus) {
      setLoading(true);
      // Attempt reconnection after 3 seconds
      setTimeout(() => {
        reconnect();
      }, 3000);
    }
  }, [connectionStatus, reconnect]);

  // Check if the frame is recent (within the last 3 seconds - increased for better resilience)
  const isFrameRecent = frame && lastFrameTime.current && (Date.now() - lastFrameTime.current < 3000);

  // Create status text
  const getStatusText = () => {
    if (!connectionStatus) return "Connecting to server...";
    if (!isFrameRecent && !frame) return "Waiting for camera feed...";
    if (!isFrameRecent) return "Reconnecting to camera...";
    return null;
  };

  const statusText = getStatusText();

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
            {statusText || 'Waiting for camera feed...'}
          </div>
        </>
      ) : isFrameRecent && frame ? (
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
        <div className="absolute inset-0 flex items-center justify-center text-white bg-zinc-800/80">
          <p className="text-sm">{statusText || "No camera feed available"}</p>
        </div>
      )}
    </div>
  );
}