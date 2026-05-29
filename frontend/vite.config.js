import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API + websocket to the FastAPI backend on :8000.
// Production build emits static assets the FastAPI app serves directly.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
