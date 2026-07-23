import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const python = process.env.NEXUSFLOW_PYTHON || ".venv/bin/python";
const databasePath = join(tmpdir(), `nexusflow-e2e-${process.pid}.db`);

export default defineConfig({
  testDir: "./frontend/tests",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8765`,
      env: { NEXUSFLOW_DB_PATH: databasePath },
      url: "http://127.0.0.1:8765/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
