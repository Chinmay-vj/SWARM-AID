/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the backend through a same-origin proxy, so the backend keeps
// SWARM_CORS_ORIGINS empty. Override the target with SWARM_BACKEND_URL (server-side only,
// never exposed to the browser bundle).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.SWARM_BACKEND_URL || "http://127.0.0.1:8000";
  const proxy = {
    "/api": { target, changeOrigin: false },
    "/health": { target, changeOrigin: false },
    "/ws": { target: target.replace(/^http/, "ws"), ws: true },
  };
  // Applied to the production build served by `vite preview`. The dev server omits CSP because
  // React Fast Refresh injects an inline preamble.
  const securityHeaders = {
    "Content-Security-Policy":
      "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; " +
      "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
  };
  return {
    plugins: [react()],
    server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
    preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy, headers: securityHeaders },
    build: { sourcemap: false, chunkSizeWarningLimit: 700 },
    test: {
      environment: "jsdom",
      globals: false,
      setupFiles: ["./tests/setup.ts"],
      include: ["tests/unit/**/*.test.ts", "tests/integration/**/*.test.tsx"],
      restoreMocks: true,
    },
  };
});
