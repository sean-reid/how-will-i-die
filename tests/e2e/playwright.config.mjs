import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const webDir = fileURLToPath(new URL("../../web", import.meta.url));

export default defineConfig({
  testDir: ".",
  timeout: 30000,
  fullyParallel: true,
  webServer: {
    command: `python3 -m http.server 8765 --directory ${webDir}`,
    port: 8765,
    reuseExistingServer: true,
  },
  use: {
    baseURL: "http://localhost:8765",
    ...devices["Desktop Chrome"],
    viewport: { width: 1100, height: 820 },
  },
});
