import { defineConfig } from '@playwright/test';
import path from 'node:path';
export default defineConfig({
  testDir: './e2e', timeout: 60000, workers: 1,
  globalTeardown: './e2e/global-teardown.ts',
  reporter: [['list'], ['html', { outputFolder: '../recovery/viewer-verification/report', open: 'never' }], ['json',{outputFile:'../recovery/viewer-verification/results.json'}]],
  outputDir: '../recovery/viewer-verification/results',
  use: { baseURL: 'http://127.0.0.1:8016', channel: 'msedge', trace: 'retain-on-failure', screenshot: 'on', viewport: { width: 1280, height: 720 } },
  webServer: { command: `"${path.resolve('../.venv/Scripts/python.exe')}" "${path.resolve('../backend/e2e/viewer_server.py')}"`, url: 'http://127.0.0.1:8016/__e2e/health', reuseExistingServer: false, timeout: 30000 },
});
