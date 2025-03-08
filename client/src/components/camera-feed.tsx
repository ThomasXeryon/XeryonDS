import { useEffect, useRef } from "react";
import { useWebSocket } from "./useWebSocket"; // Assuming this component exists

export function CameraFeed({ stationId, station }: { stationId: number; station?: { rpiId: number } }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imageSrc, setImageSrc] = useState(""); // Added state for image source
  const [error, setError] = useState("");  //Added state for error handling

  useEffect(() => {
    if (!stationId) return;

    // Standard polling fallback
    const fetchImage = async () => {
      try {
        setError(null);
        const response = await fetch(`/api/stations/${stationId}/camera`);
        if (!response.ok) {
          throw new Error('Failed to fetch camera image');
        }
        const imageBlob = await response.blob();
        const imageUrl = URL.createObjectURL(imageBlob);
        setImageSrc(imageUrl);
      } catch (err) {
        console.error('Error fetching camera image:', err);
        setError('Could not load camera feed');
      }
    };

    // Use WebSocket for real-time camera feed if available
    const { socket } = useWebSocket();

    const handleWebSocketMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'camera_frame' && data.rpiId === station?.rpiId) {
          // Update image from base64
          setImageSrc(`data:image/jpeg;base64,${data.frame}`);
        }
      } catch (err) {
        console.error('Error processing WebSocket message:', err);
      }
    };

    // Add event listener for WebSocket messages
    if (socket) {
      socket.addEventListener('message', handleWebSocketMessage);
    }

    fetchImage(); // Initial fetch
    const interval = setInterval(fetchImage, 1000); // Fallback polling

    return () => {
      clearInterval(interval);
      if (socket) {
        socket.removeEventListener('message', handleWebSocketMessage);
      }
    };
  }, [stationId, station?.rpiId]);

  return (
    <div className="w-full h-full bg-muted rounded-lg overflow-hidden">
      {error ? (
        <div>{error}</div>
      ) : (
        <img
          ref={imgRef}
          alt="Camera Feed"
          className="w-full h-full object-contain"
          src={imageSrc} // Use the state variable for the image source
        />
      )}
    </div>
  );
}