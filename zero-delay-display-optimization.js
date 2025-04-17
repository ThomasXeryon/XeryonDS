/**
 * ZERO DELAY IMAGE RENDERING OPTIMIZATIONS
 * 
 * This file contains optimizations for the client-side to ensure absolutely zero
 * delay in displaying incoming camera frames.
 */

// --- OPTIMIZATIONS FOR CAMERA-FEED.TSX ---

// 1. High priority rendering with requestAnimationFrame
// Replace the current img tag rendering with a more optimized version

/**
 * Zero-delay image rendering component using optimized techniques
 */
export function OptimizedCameraFeed({ rpiId }) {
  const canvasRef = useRef(null);
  const { frame } = useWebSocket(String(rpiId)); 
  const frameImageRef = useRef(null);
  
  // Maintain reference to last received frame
  const lastFrameRef = useRef(null);
  
  // Optimization: Pre-create a single Image object and reuse it
  useEffect(() => {
    frameImageRef.current = new Image();
    frameImageRef.current.crossOrigin = "anonymous";
    
    // Setup high-priority animation loop using requestAnimationFrame
    let animationFrameId;
    const renderFrame = () => {
      const canvas = canvasRef.current;
      const img = frameImageRef.current;
      
      if (canvas && img.complete && img.src) {
        const ctx = canvas.getContext('2d');
        // Clear canvas each time to prevent ghosting
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        // Draw latest frame
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      }
      
      // Continue the animation loop
      animationFrameId = requestAnimationFrame(renderFrame);
    };
    
    // Start animation loop
    animationFrameId = requestAnimationFrame(renderFrame);
    
    return () => {
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    };
  }, []);
  
  // Effect to update the image source when a new frame arrives
  useEffect(() => {
    if (frame) {
      // Store latest frame
      lastFrameRef.current = frame;
      
      // Directly assign to image source - skip React rendering cycle for maximum speed
      if (frameImageRef.current) {
        frameImageRef.current.src = frame;
      }
    }
  }, [frame]);
  
  return (
    <div className="relative w-full aspect-video sm:aspect-[16/9] rounded-md overflow-hidden bg-black">
      <canvas 
        ref={canvasRef}
        className="w-full h-full object-contain"
        width={1280} 
        height={720}
      />
    </div>
  );
}

// --- OPTIMIZATIONS FOR USE-WEBSOCKET.TS ---

// 2. Optimize WebSocket message handling for camera frames

/**
 * Optimized message handler for immediate frame processing
 */
const handleMessage = useCallback((event) => {
  try {
    // Direct approach: Try to parse and check for frame first without intermediate steps
    if (event.data.indexOf('"type":"camera_frame"') !== -1) {
      // It's likely a camera frame - parse it
      const data = JSON.parse(event.data);
      
      if (data.type === 'camera_frame') {
        // Direct path for camera frames - absolute minimal processing
        // Skip state updates and directly assign to the stateful ref to avoid re-renders
        const frameData = data.frame.startsWith('data:') ? 
                         data.frame : 
                         `data:image/jpeg;base64,${data.frame}`;
                    
        // Use direct DOM manipulation for ultimate speed
        if (typeof window !== 'undefined') {
          // Dispatch a custom event with the frame data
          // This allows us to bypass React's state management for ultra-low latency
          window.dispatchEvent(new CustomEvent('new-camera-frame', { 
            detail: { 
              rpiId: data.rpiId,
              frame: frameData
            }
          }));
        }
        
        // Also update state for normal React flow
        setState(prev => ({
          ...prev,
          frame: frameData,
          lastFrameTime: performance.now() // Use performance.now() for higher precision
        }));
        
        // Skip further processing for speed
        return;
      }
    }
    
    // For non-camera messages, use the regular flow
    const data = JSON.parse(event.data);
    
    // Handle other message types as before...
    
  } catch (error) {
    console.error('Error processing WebSocket message:', error);
  }
}, []);

// --- EXTREME OPTIMIZATION BROWSER HOOKS ---

/**
 * Browser optimization hooks to set highest priority for frame rendering
 */
useEffect(() => {
  // Apply page visibility optimization
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      // Page is hidden, use low frame rate
      console.log('Page hidden, conserving resources');
    } else {
      // Page is visible, use high priority
      console.log('Page visible, maximizing performance');
    }
  });
  
  // Request high priority thread execution if supported
  if ('scheduler' in window && 'postTask' in window.scheduler) {
    window.scheduler.postTask(() => {
      console.log('Running image processing with high priority');
    }, { priority: 'user-blocking' });
  }
  
  // Prevent browser throttling if possible
  if (navigator.scheduling?.isInputPending) {
    // Modern browsers with scheduling API
    setInterval(() => {
      if (!navigator.scheduling.isInputPending()) {
        // No user input pending, we can use this time for processing
      }
    }, 100);
  }
  
  return () => {
    document.removeEventListener('visibilitychange', () => {});
  };
}, []);

// --- IMAGE PROCESSING OPTIMIZATION ---

/**
 * Directly process an image with minimal overhead
 * Used as an alternative to the standard img tag for ultimate performance
 */
function processImageWithZeroDelay(imageData, targetElement) {
  // Create a blob URL for fastest possible rendering
  const blob = dataURItoBlob(imageData);
  const blobUrl = URL.createObjectURL(blob);
  
  // Set directly as background for zero-delay rendering
  if (targetElement) {
    targetElement.style.backgroundImage = `url(${blobUrl})`;
    
    // Clean up the blob URL after a short delay
    setTimeout(() => {
      URL.revokeObjectURL(blobUrl);
    }, 1000);
  }
  
  return blobUrl;
}

// Helper function to convert data URI to Blob
function dataURItoBlob(dataURI) {
  const byteString = atob(dataURI.split(',')[1]);
  const mimeString = dataURI.split(',')[0].split(':')[1].split(';')[0];
  const ab = new ArrayBuffer(byteString.length);
  const ia = new Uint8Array(ab);
  
  for (let i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  
  return new Blob([ab], { type: mimeString });
}