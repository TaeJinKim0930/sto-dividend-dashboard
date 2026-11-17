import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5180, proxy: { "/agent": "http://localhost:8700", "/api": "http://localhost:8700" } },
});
