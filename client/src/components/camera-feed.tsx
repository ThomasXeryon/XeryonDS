import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [loading, setLoading] = useState(true);
  const { connectionStatus, frame, wsRef } = useWebSocket(String(rpiId));
  const lastFrameTime = useRef<number | null>(null);
  const lastValidFrame = useRef<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);

  useEffect(() => {
    if (frame) {
      const now = Date.now();
      lastFrameTime.current = now;

      // Skip frame if we already have a more recent one
      if (lastValidFrame.current && frame.timestamp < lastValidFrame.current.timestamp) {
        return;
      }

      lastValidFrame.current = frame;
      setLoading(false);
      setIsReconnecting(false);

      // Request next frame immediately
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: "request_frame",
          timestamp: now
        }));
      }
    } else if (lastFrameTime.current && (Date.now() - lastFrameTime.current > 5000)) {
      // Just set reconnecting state if no frames
      setIsReconnecting(true);
    }
  }, [frame, wsRef]);

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
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading && !lastValidFrame.current ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
            {statusText || 'Waiting for camera feed...'}
          </div>
        </>
      ) : (isFrameRecent && frame) || lastValidFrame.current ? (
        <>
          <img
            src={isFrameRecent && frame ? frame : lastValidFrame.current!}
            alt="Camera Feed"
            className="w-full h-full object-contain"
            onError={(e) => {
              console.error("[CameraFeed] Error loading frame:", e);
              setLoading(true);
            }}
            onLoad={() => console.log("[CameraFeed] Frame loaded successfully for RPi:", rpiId)}
          />

          {/* Reconnecting overlay that shows in corner when connection is lost */}
          {showReconnectingOverlay && (
            <div className="absolute top-2 right-2 bg-red-500/80 text-white px-2 py-1 rounded text-xs">
              Reconnecting camera...
            </div>
          )}
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-white bg-zinc-800/80">
          <p className="text-sm">{statusText || "No camera feed available"}</p>
        </div>
      )}
    </div>
  );
}