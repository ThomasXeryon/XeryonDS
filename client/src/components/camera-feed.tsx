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
    if (!socket || !rpiId) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'camera_frame' && String(data.rpiId) === String(rpiId)) {
          console.log(`Received frame from RPi ${rpiId}, size: ${data.frame?.length || 0} bytes`);

          if (data.frame) {
            const frameUrl = `data:image/jpeg;base64,${data.frame}`;
            setFrame(frameUrl);
            setLoading(false);
          }
        }
      } catch (err) {
        console.error('Frame processing error:', err);
      }
    };

    socket.addEventListener('message', handleMessage);
    return () => socket.removeEventListener('message', handleMessage);
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
          key={frame} // Force re-render when frame updates 
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          onLoad={() => console.log('Frame loaded successfully')}
          onError={(e) => {
            console.error('Image loading error:', e);
            console.log('Failed frame URL length:', frame.length);
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