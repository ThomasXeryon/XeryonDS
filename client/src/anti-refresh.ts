// Anti-refresh script to prevent Vite from refreshing the page

// Define custom Window interface with Vite properties
declare global {
  interface Window {
    __vite_hmr?: any;
    __vite_ws?: any;
  }
}

// Function to disable Vite's HMR
function disableHMR() {
  try {
    // Try to find and disable Vite's HMR
    if (window.__vite_hmr !== undefined) {
      console.log('Found Vite HMR, disabling it');
      // @ts-ignore
      window.__vite_hmr.dispose = () => console.log('HMR dispose blocked');
      // @ts-ignore
      window.__vite_hmr.reload = () => console.log('HMR reload blocked');
      // @ts-ignore
      window.__vite_hmr.hot = null;
    }

    // Check for the vite websocket
    const viteSocket = (window as any).__vite_ws;
    if (viteSocket) {
      console.log('Found Vite WebSocket, disabling it');
      // Replace the send function with a no-op
      viteSocket.send = () => {};
      // Close the socket
      viteSocket.close();
      // Clear any message handlers
      viteSocket.onmessage = null;
    }

    // Block all WebSocket connection attempts to Vite HMR
    const originalWebSocket = WebSocket;
    // @ts-ignore
    window.WebSocket = function(url: string, protocols?: string | string[]) {
      if (url.includes('__vite_hmr') || url.includes('vite-hmr')) {
        console.log('Blocked WebSocket connection to:', url);
        // Return a fake WebSocket that doesn't actually connect
        return {
          addEventListener: () => {},
          removeEventListener: () => {},
          send: () => {},
          close: () => {},
          onopen: null,
          onclose: null,
          onmessage: null,
          onerror: null,
        };
      }
      // Allow all other WebSocket connections
      return new originalWebSocket(url, protocols);
    };
    
    // For good measure, override the reload functions
    if (window.location) {
      window.location.reload = () => {
        console.log('Blocked page reload');
        return false;
      };
    }
    
    console.log('Anti-refresh protection enabled');
  } catch (error) {
    console.error('Error disabling HMR:', error);
  }
}

// Run immediately 
disableHMR();

// Also run after a delay to catch late-initialized HMR
setTimeout(disableHMR, 1000);
setTimeout(disableHMR, 5000);

// Export something to make this a proper module
export const antiRefreshEnabled = true;