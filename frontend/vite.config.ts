import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs on :8000 (uvicorn app.main:app --reload). The proxy avoids CORS in development.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
