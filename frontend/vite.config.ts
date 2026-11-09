import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the local backend (host :8000).
// Production builds rely on Nginx's /api proxy instead; the axios client
// always targets same-origin "/api", so no host or secret is baked in.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // Split heavy vendor libs into parallel-loaded chunks so the app chunk
    // stays small and the browser can fetch/reuse vendors independently.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          motion: ["framer-motion"],
          charts: ["recharts"],
        },
      },
    },
  },
});
