import { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

export function CameraFeed({ stationId, station }: { stationId: number; station?: { rpiId: number | string } }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imageSrc, setImageSrc] = useState<string>(""); 
  const [error, setError] = useState<string | null>(null);
  const { socket } = useWebSocket();

  useEffect(() => {
    if (!socket) return;

    // Set up event listener for incoming messages
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        // Check if this is a camera frame from the selected station
        if (data.type === 'camera_frame' && data.rpiId === station?.rpiId) {
          const imageData = data.frame;
          if (imageData) {
            setImageSrc(`data:image/jpeg;base64,${imageData}`);
            setError(null);
          }
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };

    socket.addEventListener('message', handleMessage);

    return () => {
      socket.removeEventListener('message', handleMessage);
    };
  }, [socket, station?.rpiId]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-[240px] bg-muted rounded-md">
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-muted">
      {!imageSrc ? (
        <Skeleton className="w-full h-full absolute top-0 left-0" />
      ) : (
        <img
          ref={imgRef}
          src={imageSrc}
          alt="Camera Feed"
          className="w-full h-full object-cover"
        />
      )}
    </div>
  );
}