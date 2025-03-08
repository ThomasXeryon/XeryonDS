import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [frame, setFrame] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { socket } = useWebSocket();

  useEffect(() => {
    if (!socket || !rpiId) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'camera_frame' && String(data.rpiId) === String(rpiId)) {
          setFrame(`data:image/jpeg;base64,${data.frame}`);
          setLoading(false);
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
        <Skeleton className="h-full w-full" />
      ) : frame ? (
        <img
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          onError={() => setFrame(null)}
        />
      ) : (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">No camera feed available</p>
        </div>
      )}
    </div>
  );
}