import React, { useState, useEffect, useRef } from 'react';

function MyComponent() {
  const wsRef = useRef(null);
  const lastMessageTime = useRef(0);
  const [state, setState] = useState({ frame: null });

  const connect = () => {
    wsRef.current = new WebSocket('ws://localhost:8080'); // Replace with your WebSocket URL

    wsRef.current.onopen = () => {
      console.log('[WebSocket] Connected');
    };

    wsRef.current.onmessage = (event) => {
      const frame = JSON.parse(event.data);
      setState({ frame });
      lastMessageTime.current = Date.now();
    };

    wsRef.current.onclose = () => {
      console.log('[WebSocket] Closed');
      wsRef.current = null; // Important for cleanup
    };

    wsRef.current.onerror = (error) => {
      console.error('[WebSocket] Error:', error);
      wsRef.current = null; // Important for cleanup
    };
  };

  useEffect(() => {
    connect();

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    // Reconnect if we haven't received a frame in 5 seconds
    const reconnectInterval = setInterval(() => {
      if (wsRef.current?.readyState !== WebSocket.OPEN || 
          (state.frame && Date.now() - lastMessageTime.current > 5000)) {
        console.log('[WebSocket] No recent frames, reconnecting...');
        connect();
      }
    }, 5000);

    return () => {
      clearInterval(pingInterval);
      clearInterval(reconnectInterval);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  return (
    <div>
      {state.frame ? (
        <p>Received Frame: {JSON.stringify(state.frame)}</p>
      ) : (
        <p>Waiting for frame...</p>
      )}
    </div>
  );
}

export default MyComponent;