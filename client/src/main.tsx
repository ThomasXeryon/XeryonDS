
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { ThemeProvider } from "@/hooks/use-theme";
import { antiRefreshEnabled } from "./anti-refresh";

// Log that anti-refresh is enabled
console.log("Anti-refresh system enabled:", antiRefreshEnabled);

// Disable HMR/Fast refresh to prevent page reloading
if (import.meta.hot) {
  // This tells Vite not to replace the entire page when modules change
  import.meta.hot.accept(() => {
    // Don't do anything - effectively disabling refresh
    console.log("Update prevented - keeping current state");
  });
}

// Persist app state across HMR updates
let root;
if (!root) {
  root = createRoot(document.getElementById("root")!);
  root.render(
    <React.StrictMode>
      <ThemeProvider defaultTheme="light">
        <App />
      </ThemeProvider>
    </React.StrictMode>
  );
}

// Add unload prevention
window.addEventListener("beforeunload", (e) => {
  e.preventDefault();
  e.returnValue = ""; // Chrome requires returnValue to be set
  return ""; // Legacy browsers
});
