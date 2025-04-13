import React, { useEffect, useRef, useState } from "react";

interface ConnectionVisualizerProps {
  totalLatency: number;
  isConnected: boolean;
}

export function ConnectionVisualizer({ totalLatency, isConnected }: ConnectionVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [animationFrame, setAnimationFrame] = useState<number | null>(null);
  const lastPingTime = useRef<number>(Date.now());
  const pingHistory = useRef<number[]>([]);
  
  // Add new ping to history
  useEffect(() => {
    if (totalLatency > 0) {
      // Only update if it's been at least 1 second since last ping
      const now = Date.now();
      if (now - lastPingTime.current > 1000) {
        lastPingTime.current = now;
        pingHistory.current = [...pingHistory.current.slice(-30), totalLatency];
      }
    }
  }, [totalLatency]);
  
  // Animation effect
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Setup canvas size
    const resizeCanvas = () => {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
    };
    
    // Initial setup
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    // Animation function
    let packetPosition = 0;
    const animate = () => {
      if (!canvas || !ctx) return;
      
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      if (!isConnected) {
        // Show disconnected state
        ctx.fillStyle = 'rgba(220, 53, 69, 0.2)'; // Red for disconnected
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // Draw crossed lines
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(220, 53, 69, 0.7)';
        ctx.lineWidth = 2;
        ctx.moveTo(0, 0);
        ctx.lineTo(canvas.width, canvas.height);
        ctx.moveTo(canvas.width, 0);
        ctx.lineTo(0, canvas.height);
        ctx.stroke();
        
        const frame = requestAnimationFrame(animate);
        setAnimationFrame(frame);
        return;
      }
      
      // Background
      ctx.fillStyle = 'rgba(13, 110, 253, 0.05)'; // Very light blue
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // Draw path
      const pathY = canvas.height / 2;
      const pathHeight = 4;
      
      // Draw base path
      ctx.fillStyle = 'rgba(13, 110, 253, 0.3)';
      ctx.fillRect(10, pathY - pathHeight/2, canvas.width - 20, pathHeight);
      
      // Draw connection points
      const serverX = canvas.width / 2;
      const userX = 10;
      const xeryonX = canvas.width - 10;
      
      // User point
      ctx.beginPath();
      ctx.arc(userX, pathY, 6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgb(13, 110, 253)';
      ctx.fill();
      
      // Server point
      ctx.beginPath();
      ctx.arc(serverX, pathY, 6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgb(13, 110, 253)';
      ctx.fill();
      
      // Xeryon point
      ctx.beginPath();
      ctx.arc(xeryonX, pathY, 6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgb(13, 110, 253)';
      ctx.fill();
      
      // Animate data packet
      // First half of journey: User -> Server -> Xeryon
      const halfPath = canvas.width / 2 - 10;
      
      if (packetPosition < halfPath) {
        if (packetPosition < serverX - userX) {
          // User -> Server
          const x = userX + packetPosition;
          // Draw packet
          ctx.beginPath();
          ctx.arc(x, pathY, 3, 0, Math.PI * 2);
          ctx.fillStyle = 'rgb(255, 193, 7)'; // Yellow for command
          ctx.fill();
        } else {
          // Server -> Xeryon
          const progressInSecondSegment = packetPosition - (serverX - userX);
          const x = serverX + progressInSecondSegment;
          // Draw packet
          ctx.beginPath();
          ctx.arc(x, pathY, 3, 0, Math.PI * 2);
          ctx.fillStyle = 'rgb(255, 193, 7)'; // Yellow for command
          ctx.fill();
        }
      } else {
        // Second half of journey: Xeryon -> Server -> User
        const returnProgress = packetPosition - halfPath;
        
        if (returnProgress < xeryonX - serverX) {
          // Xeryon -> Server
          const x = xeryonX - returnProgress;
          // Draw packet
          ctx.beginPath();
          ctx.arc(x, pathY, 3, 0, Math.PI * 2);
          ctx.fillStyle = 'rgb(25, 135, 84)'; // Green for video
          ctx.fill();
        } else {
          // Server -> User
          const progressInFinalSegment = returnProgress - (xeryonX - serverX);
          const x = serverX - progressInFinalSegment;
          // Draw packet
          ctx.beginPath();
          ctx.arc(x, pathY, 3, 0, Math.PI * 2);
          ctx.fillStyle = 'rgb(25, 135, 84)'; // Green for video
          ctx.fill();
        }
      }
      
      // Reset position or increment
      packetPosition = (packetPosition + 2) % (canvas.width - 20);
      
      // Draw labels
      ctx.font = '10px Arial';
      ctx.textAlign = 'center';
      ctx.fillStyle = '#555';
      
      ctx.fillText('User', userX, pathY - 12);
      ctx.fillText('Server', serverX, pathY - 12);
      ctx.fillText('Xeryon', xeryonX, pathY - 12);
      
      // Draw ping history graph
      if (pingHistory.current.length > 1) {
        const graphHeight = 40;
        const graphY = canvas.height - graphHeight - 5;
        const maxPing = Math.max(...pingHistory.current, 200); // At least 200ms for scale
        
        // Draw graph background
        ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
        ctx.fillRect(10, graphY, canvas.width - 20, graphHeight);
        
        // Draw ping line
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(13, 110, 253, 0.7)';
        ctx.lineWidth = 1;
        
        pingHistory.current.forEach((ping, i) => {
          const x = 10 + (i / (pingHistory.current.length - 1)) * (canvas.width - 20);
          const y = graphY + graphHeight - (ping / maxPing) * graphHeight;
          
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });
        
        ctx.stroke();
        
        // Draw latest ping value
        const latestPing = pingHistory.current[pingHistory.current.length - 1];
        ctx.font = '9px Arial';
        ctx.textAlign = 'right';
        ctx.fillStyle = '#333';
        ctx.fillText(`${latestPing.toFixed(1)}ms`, canvas.width - 12, graphY + 10);
      }
      
      const frame = requestAnimationFrame(animate);
      setAnimationFrame(frame);
    };
    
    const frame = requestAnimationFrame(animate);
    setAnimationFrame(frame);
    
    return () => {
      if (animationFrame !== null) {
        cancelAnimationFrame(animationFrame);
      }
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [isConnected]);
  
  return (
    <canvas 
      ref={canvasRef} 
      className="w-full h-[120px] rounded-lg"
      style={{ 
        border: '1px solid rgba(0,0,0,0.1)',
        background: '#f8f9fa'
      }}
    />
  );
}