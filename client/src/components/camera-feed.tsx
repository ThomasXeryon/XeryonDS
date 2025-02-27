import { useEffect, useRef } from "react";

export function CameraFeed({ stationId }: { stationId: number }) {
  const imgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const interval = setInterval(() => {
      if (imgRef.current) {
        // Add timestamp to prevent caching
        imgRef.current.src = `/api/stations/${stationId}/camera?t=${Date.now()}`;
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [stationId]);

  return (
    <div className="aspect-video bg-muted rounded-lg overflow-hidden">
      <img
        ref={imgRef}
        alt="Camera Feed"
        className="w-full h-full object-cover"
        src={`/api/stations/${stationId}/camera`}
      />
    </div>
  );
}
