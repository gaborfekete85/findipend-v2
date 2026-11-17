/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: "..",
  server: { host: true, port: 3000 },
  preview: { host: true, port: 3000 },
  test: { environment: "jsdom" },
});
