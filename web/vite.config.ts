/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run dev` proxies the API to a local server started with DEV_USER (see the repo README).
export default defineConfig({
  base: "/",
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8094" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    // One bundle on purpose. A manualChunks split of react and recharts (tried first) made the chunks import
    // each other in a cycle and the page came up blank: "reading '__SECRET_INTERNALS_DO_NOT_USE...'".
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
