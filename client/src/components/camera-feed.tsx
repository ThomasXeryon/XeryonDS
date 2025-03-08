
import React, { useState, useEffect } from 'react';
import { Skeleton } from "@/components/ui/skeleton";
import { useWebSocket } from "@/hooks/use-websocket";

interface CameraFeedProps {
  rpiId: string | number;
  stationId?: string | number;
}

export function CameraFeed({ rpiId, stationId }: CameraFeedProps) {
  const [frame, setFrame] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { socket, connectionStatus } = useWebSocket();
  
  useEffect(() => {
    if (!socket || !rpiId) {
      console.log("No socket or rpiId available");
      return;
    }

    console.log(`CameraFeed: Setting up camera feed listener for RPI ${rpiId}`);
    
    // Handler for WebSocket messages
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log("WebSocket message received:", data.type, data.rpiId);
        
        // Check if this is a camera frame from the selected station
        if (data.type === 'camera_frame' && data.rpiId == rpiId) {
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
  
  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading ? (
        <div className="flex items-center justify-center h-full">
          <Skeleton className="w-full h-full absolute" />
          <p className="text-white/70 z-10 text-sm">Waiting for camera feed...</p>
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">{error}</p>
        </div>
      ) : frame ? (
        <img 
          src={frame} 
          alt={`Camera feed from RPI ${rpiId}`} 
          className="w-full h-full object-contain"
        />
      ) : (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">No camera feed available</p>
        </div>
      )}
      <div className="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
        {connectionStatus ? "Connected" : "Disconnected"} (RPI-{rpiId})
      </div>
    </div>
  );
}
