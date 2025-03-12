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
  const lastValidFrame = useRef<string | null>(null);
  const [isReconnecting, setIsReconnecting] = useState(false);

  useEffect(() => {
    if (frame) {
      lastFrameTime.current = Date.now();
      lastValidFrame.current = frame; // Store the last valid frame
      setLoading(false); // Stop loading when frame arrives
      setIsReconnecting(false);
    }
  }, [frame]);

  // Send message to server to watch this specific RPI
  useEffect(() => {
    if (connectionStatus && rpiId) {
      // Tell the server which station this client wants to watch
      const socket = (window as any).wsConnection;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
          type: 'watch_station',
          rpiId: rpiId
        }));
        console.log(`Sent watch_station request for RPi ${rpiId}`);
      }
    }
  }, [connectionStatus, rpiId]);

  // Show reconnecting state when connection is lost and attempt reconnection
  useEffect(() => {
    if (!connectionStatus) {
      setIsReconnecting(true);
      // Attempt reconnection after 3 seconds
      setTimeout(() => {
        reconnect();
      }, 3000);
    }
  }, [connectionStatus, reconnect]);

  // Check if the frame is recent (within the last 5 seconds - increased for better resilience)
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