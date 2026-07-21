import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-only, opt-in API proxy. When SOLAR_MOCK_API is set (e.g. a local mock
// status-server), API routes are proxied there so the UI can be driven against
// fixture data. Inert by default — it never affects `vite build` output.
const mockTarget = process.env.SOLAR_MOCK_API;
const apiRoutes = [
  "/status",
  "/sprints",
  "/orchestration",
  "/events",
  "/usage",
  "/settings",
  "/intake",
];

export default defineConfig({
  base: "/static/p0-app/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: Number(process.env.PORT) || 5173,
    ...(mockTarget
      ? {
          proxy: Object.fromEntries(
            apiRoutes.map((route) => [
              route,
              { target: mockTarget, changeOrigin: true },
            ]),
          ),
        }
      : {}),
  },
  build: {
    outDir: "../static/p0-app",
    assetsDir: "assets",
    emptyOutDir: true,
    sourcemap: false,
  },
});
