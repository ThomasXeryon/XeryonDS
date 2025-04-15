
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { ThemeProvider } from "@/hooks/use-theme";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider defaultTheme="light">
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
