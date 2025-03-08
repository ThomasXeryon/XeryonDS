import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [frame, setFrame] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { socket, connectionStatus } = useWebSocket();

  useEffect(() => {
    if (!socket || !rpiId) {
      console.log("[CameraFeed] No socket or rpiId available", { 
        hasSocket: !!socket, 
        rpiId,
        socketState: socket?.readyState 
      });
      return;
    }

    console.log("[CameraFeed] Setting up frame listener for RPi:", rpiId);
    setLoading(true);

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        // Only log frame info if it's a camera frame for our RPi
        if (data.type === 'camera_frame' && String(data.rpiId) === String(rpiId)) {
          console.log("[CameraFeed] Processing frame:", { 
            messageRpiId: data.rpiId,
            currentRpiId: rpiId,
            hasFrame: !!data.frame,
            frameSize: data.frame?.length || 0,
            isDataUrl: data.frame?.startsWith('data:')
          });

          if (!data.frame) {
            console.warn("[CameraFeed] Frame data missing");
            return;
          }

          // The server should already send us a proper data URL
          // But let's verify it's in the correct format
          if (!data.frame.startsWith('data:image/')) {
            console.error("[CameraFeed] Invalid frame format - expected data URL");
            return;
          }

          console.log("[CameraFeed] Setting new frame");
          setFrame(data.frame);
          setLoading(false);
        }
      } catch (err) {
        console.error("[CameraFeed] Message processing error:", err);
      }
    };

    socket.addEventListener('message', handleMessage);
    console.log("[CameraFeed] WebSocket listener added");

    return () => {
      console.log("[CameraFeed] Cleaning up WebSocket listener");
      socket.removeEventListener('message', handleMessage);
    };
  }, [socket, rpiId]);

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading ? (
        <>
          <Skeleton className="h-full w-full" />
          <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
            Waiting for camera feed...
          </div>
        </>
      ) : frame ? (
        <img
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          onError={(e) => {
            console.error("[CameraFeed] Error loading frame:", e);
            setFrame(null);
          }}
        />
      ) : (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">No camera feed available</p>
        </div>
      )}
      <div className="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
        {connectionStatus ? "Connected" : "Disconnected"}
      </div>
    </div>
  );
}