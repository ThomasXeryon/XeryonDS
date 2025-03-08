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
      console.log("No socket or rpiId available", { socket: !!socket, rpiId });
      return;
    }

    console.log("Setting up camera feed listener for RPI:", rpiId);
    setLoading(true);

    // Handler for WebSocket messages
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log("Camera feed received message:", { 
          type: data.type, 
          rpiId: data.rpiId, 
          hasFrame: !!data.frame,
          currentRpiId: rpiId
        });

        // Check if this is a camera frame and convert IDs to strings for comparison
        if (data.type === 'camera_frame' && String(data.rpiId) === String(rpiId)) {
          if (!data.frame) {
            console.warn("Received camera_frame message without frame data");
            return;
          }

          console.log(`Received frame for RPi ${data.rpiId}, matches current RPi ${rpiId}`);
          const frameData = `data:image/jpeg;base64,${data.frame}`;
          console.log("Frame data length:", frameData.length);

          // Verify the base64 data is valid before setting
          try {
            atob(data.frame); // Test if it's valid base64
            setFrame(frameData);
            setLoading(false);
          } catch (base64Error) {
            console.error("Invalid base64 data in frame:", base64Error);
          }
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };

    // Add event listener
    socket.addEventListener('message', handleMessage);
    console.log("Camera feed WebSocket listener added");

    // Clean up
    return () => {
      console.log("Removing camera feed WebSocket listener");
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
          onError={(e) => {
            console.error("Error loading camera frame:", e);
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