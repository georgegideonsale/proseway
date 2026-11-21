import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.PROSEWAY_BACKEND ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/proseway/static",
    emptyOutDir: true,
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backend,
        changeOrigin: true,
        configure: (proxy) => {
          // The backend rejects cross-origin writes; in dev the page and API live on
          // different ports, so drop the Origin header on the proxied hop.
          proxy.on("proxyReq", (req) => req.removeHeader("origin"));
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
