
import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

export function CameraFeed({ stationId, station }: { stationId: number; station?: { rpiId: number | string } }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imageSrc, setImageSrc] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const { socket, connectionStatus } = useWebSocket();

  useEffect(() => {
    if (!socket || !station?.rpiId) {
      return;
    }

    console.log("Setting up camera feed listener for RPI:", station.rpiId);

    // Handler for WebSocket messages
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        
        // Check if this is a camera frame from the selected station
        if (data.type === 'camera_frame' && data.rpiId === station.rpiId) {
          setImageSrc(`data:image/jpeg;base64,${data.frame}`);
          setError(null);
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
  }, [socket, station?.rpiId]);

  // Show loading skeleton if no image yet
  if (!imageSrc && !error) {
    return (
      <div className="relative w-full h-[240px] rounded-md overflow-hidden bg-black">
        <Skeleton className="h-full w-full" />
      </div>
    );
  }

  // Show error message if there's an error
  if (error) {
    return (
      <div className="flex items-center justify-center h-[240px] bg-muted rounded-md">
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  // Display the camera feed
  return (
    <div className="relative w-full h-[240px] rounded-md overflow-hidden bg-black">
      {imageSrc ? (
        <img
          ref={imgRef}
          src={imageSrc}
          alt="Camera Feed"
          className="w-full h-full object-contain"
        />
      ) : (
        <div className="flex items-center justify-center h-full">
          <p className="text-sm text-gray-400">No camera feed available</p>
        </div>
      )}
      <div className="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
        {connectionStatus ? "Connected" : "Disconnected"}
      </div>
    </div>
  );
}
