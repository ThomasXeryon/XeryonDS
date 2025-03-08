
import React, { useState, useEffect, useCallback } from 'react';
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
      return;
    }

    console.log("Setting up camera feed listener for RPI:", rpiId);
    setLoading(true);

    // Handler for WebSocket messages
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        
        // Check if this is a camera frame from the selected station
        if (data.type === 'camera_frame' && data.rpiId === rpiId) {
          setFrame(`data:image/jpeg;base64,${data.frame}`);
          setLoading(false);
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };

    // Add event listener
    socket.addEventListener('message', handleMessage);

    // Clean up
    return () => {
      socket.removeEventListener('message', handleMessage);
    };
  }, [socket, rpiId]);

  if (loading) {
    return (
      <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
        <Skeleton className="h-full w-full" />
        <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
          Waiting for camera feed...
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {frame ? (
        <img
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
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
