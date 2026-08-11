import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const BACKEND_ORIGIN = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // `ws: true` keeps /api/ws working through the dev proxy; without it the
      // upgrade request is answered as plain HTTP and the live feed never opens.
      "/api": {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    port: 4173,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
  },
});
