import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Overridable so a second dev server can run beside a first one without the two
// proxying to the same API. `npm run shots` uses this: it boots its own seeded
// backend and must not talk to whatever is already on 8000.
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: FRONTEND_PORT,
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
  test: {
    // jsdom, because every test here drives real DOM: modals portal into
    // document.body and the events provider needs window/WebSocket.
    environment: "jsdom",
    // Globals are on so Testing Library registers its automatic cleanup;
    // the test files still import describe/it/expect explicitly.
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    // The default 5s is measured per test but spent on a machine running the
    // whole suite in parallel. The slowest test here types a multi-line
    // textarea through userEvent: ~2s alone, over 5s under load. It failed on
    // a full run and passed in isolation, which is a flake, not a regression —
    // and a suite that goes red for scheduling reasons stops being evidence.
    testTimeout: 15_000,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
    },
  },
});
