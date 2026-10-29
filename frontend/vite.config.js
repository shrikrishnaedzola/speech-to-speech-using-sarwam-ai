import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The dev server forwards /api (HTTP + WebSocket) to the FastAPI backend,
// so the browser never talks to Sarvam and never sees the API key.
const backendTarget = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": { target: backendTarget, changeOrigin: true, ws: true },
    },
  },
});
