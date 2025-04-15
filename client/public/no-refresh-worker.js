// A service worker to prevent Vite's HMR from refreshing the page

self.addEventListener('install', (event) => {
  // Skip waiting, activate this worker immediately
  self.skipWaiting();
  console.log('[SW] Service worker installed');
});

self.addEventListener('activate', (event) => {
  // Claim clients so this service worker controls all pages immediately
  event.waitUntil(clients.claim());
  console.log('[SW] Service worker activated');
});

// Track which HMR-related scripts we've already handled
const handledScripts = new Set();

// Intercept fetch requests
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Only intercept HMR-related requests that might trigger page reloads
  if (url.pathname.includes('__vite_hmr') || 
      url.pathname.includes('hot-update') ||
      url.pathname.includes('@vite/client')) {
    
    // For HMR ping requests, return a fake response
    if (url.pathname.includes('__vite_ping')) {
      event.respondWith(new Response(JSON.stringify({ success: true }), {
        headers: { 'Content-Type': 'application/json' }
      }));
      return;
    }
    
    // For @vite/client, provide a fake minimal implementation
    if (url.pathname.includes('@vite/client')) {
      if (handledScripts.has(event.request.url)) {
        return; // Already handled, don't duplicate
      }
      
      handledScripts.add(event.request.url);
      
      // Create a minimal fake vite client module to prevent errors
      const fakeViteClient = `
        // Fake Vite client that doesn't refresh the page
        export const createHotContext = () => ({
          accept: () => {},
          dispose: () => {},
          invalidate: () => {},
          on: () => {},
          prune: () => {}
        });
        
        export const injectQuery = (url) => url;
        
        console.log('[SW] Provided fake Vite client module');
      `;
      
      event.respondWith(new Response(fakeViteClient, {
        headers: { 'Content-Type': 'application/javascript' }
      }));
      return;
    }
    
    // For other HMR requests, just block them
    event.respondWith(new Response('// HMR update intercepted', {
      status: 200,
      headers: { 'Content-Type': 'application/javascript' }
    }));
    return;
  }
  
  // Let all non-HMR requests pass through normally
  return;
});