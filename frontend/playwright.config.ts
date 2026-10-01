import { defineConfig } from '@playwright/test';
import path from 'node:path';
export default defineConfig({
  testDir: './e2e', timeout: 60000, workers: 1,
  // Screenshot review (playwright.visual.config.ts) is not part of the behaviour suite.
  testIgnore: ['**/visual/**'],
  globalTeardown: './e2e/global-teardown.ts',
  reporter: [['list'], ['html', { outputFolder: '../test-output/viewer-verification/report', open: 'never' }], ['json',{outputFile:'../test-output/viewer-verification/results.json'}]],
  outputDir: '../test-output/viewer-verification/results',
  use: { baseURL: 'http://127.0.0.1:8016', channel: 'msedge', trace: 'retain-on-failure', screenshot: 'on', viewport: { width: 1280, height: 720 } },
  webServer: { command: `"${path.resolve('../.venv/Scripts/python.exe')}" "${path.resolve('../backend/e2e/viewer_server.py')}"`, url: 'http://127.0.0.1:8016/__e2e/health', reuseExistingServer: false, timeout: 30000 },
});
