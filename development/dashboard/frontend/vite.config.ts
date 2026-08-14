import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8033",
        changeOrigin: true,
        // no rewrite: versioned contract is served under /api/v1/... on the backend
      },
    },
  },
});
