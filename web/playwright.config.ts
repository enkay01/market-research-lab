import { defineConfig } from "playwright/test";

const port = process.env.PLAYWRIGHT_PORT || "5173";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
  },
  webServer: {
    command: `npx vite --port ${port} --host 127.0.0.1`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: !process.env.PLAYWRIGHT_PORT,
    timeout: 30000,
  },
});
