import React, { useState, useEffect } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { Skeleton } from "@/components/ui/skeleton";

interface CameraFeedProps {
  rpiId: string | number;
}

export function CameraFeed({ rpiId }: CameraFeedProps) {
  const [frame, setFrame] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { socket, connectionStatus } = useWebSocket();

  useEffect(() => {
    if (!socket) return;

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'camera_frame' && String(data.rpi_id) === String(rpiId)) {
          setFrame(`data:image/jpeg;base64,${data.frame}`);
          setLoading(false);
          setError(null);
        }
      } catch (err) {
        console.error('Frame error:', err);
        setError('Failed to process camera frame');
        setLoading(false);
      }
    };

    socket.addEventListener('message', handleMessage);
    return () => socket.removeEventListener('message', handleMessage);
  }, [socket, rpiId]);

  // Reset loading state when connection status changes
  useEffect(() => {
    if (!connectionStatus) {
      setLoading(true);
      setError('Connecting to camera feed...');
    }
  }, [connectionStatus]);

  return (
    <div className="relative w-full aspect-video rounded-md overflow-hidden bg-black">
      {loading ? (
        <Skeleton className="h-full w-full" />
      ) : error ? (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">{error}</p>
        </div>
      ) : frame ? (
        <img
          src={frame}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          onError={() => {
            setFrame(null);
            setError('Failed to display camera frame');
          }}
        />
      ) : (
        <div className="flex items-center justify-center h-full text-white/70">
          <p className="text-sm">No camera feed available</p>
        </div>
      )}
    </div>
  );
}