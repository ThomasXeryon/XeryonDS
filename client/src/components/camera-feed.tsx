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
        console.log('Camera feed received message:', {
          type: data.type,
          rpiId: data.rpiId,
          hasFrame: !!data.frame,
          frameLength: data.frame?.length,
          matchesRpiId: String(data.rpiId) === String(rpiId)
        });

        if (data.type === 'camera_frame' && String(data.rpiId) === String(rpiId)) {
          if (!data.frame) {
            console.warn('Received camera frame message without frame data');
            return;
          }

          // Basic base64 validation
          if (!/^[A-Za-z0-9+/=]+$/.test(data.frame)) {
            console.error('Invalid base64 data received:', {
              frameStart: data.frame.substring(0, 50) + '...',
              length: data.frame.length
            });
            return;
          }

          // Try to decode base64 to validate format
          try {
            const decoded = atob(data.frame);
            console.log('Base64 decoded successfully:', {
              decodedLength: decoded.length,
              isJPEG: decoded.startsWith('\xFF\xD8\xFF')
            });
          } catch (e) {
            console.error('Base64 decode failed:', e);
            return;
          }

          const frameUrl = `data:image/jpeg;base64,${data.frame}`;
          console.log('Setting frame URL:', {
            frameUrlLength: frameUrl.length,
            frameStart: frameUrl.substring(0, 100) + '...',
            isDataUrl: frameUrl.startsWith('data:image/jpeg;base64,')
          });

          // Pre-validate the image
          const img = new Image();
          img.onload = () => {
            console.log('Frame validated and loaded:', {
              width: img.width,
              height: img.height,
              rpiId
            });
            setFrame(frameUrl);
            setLoading(false);
          };
          img.onerror = (error) => {
            console.error('Frame validation failed:', error);
            setFrame(null);
            setLoading(true);
          };
          img.src = frameUrl;
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
          onLoad={() => console.log('Frame rendered successfully:', { rpiId })}
          onError={(e) => {
            console.error('Image rendering error:', e);
            setFrame(null);
            setLoading(true);
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