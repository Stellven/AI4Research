import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/p0-app/",
  plugins: [react()],
  build: {
    outDir: "../static/p0-app",
    assetsDir: "assets",
    emptyOutDir: true,
    sourcemap: false
  }
});
