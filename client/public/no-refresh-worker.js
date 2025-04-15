// A service worker to prevent Vite's HMR from refreshing the page

self.addEventListener('install', (event) => {
  // Skip waiting, activate this worker immediately
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Claim clients so this service worker controls all pages immediately
  event.waitUntil(clients.claim());
});

// Intercept fetch requests
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Block HMR-related requests that might trigger page reloads
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
    
    // For other HMR requests, just block them
    event.respondWith(new Response('', {
      status: 200,
      headers: { 'Content-Type': 'application/javascript' }
    }));
    return;
  }
  
  // Let all other requests pass through normally
  return;
});