import { defineConfig } from '@playwright/test';
import path from 'node:path';

// E2E_PORT lets two worktrees verify at once; the fixture server reads the same variable.
const origin = `http://127.0.0.1:${process.env.E2E_PORT || 8016}`;
export default defineConfig({
  testDir: './e2e', timeout: 60000, workers: 1,
  // Screenshot review (playwright.visual.config.ts) is not part of the behaviour suite.
  testIgnore: ['**/visual/**'],
  globalTeardown: './e2e/global-teardown.ts',
  reporter: [['list'], ['html', { outputFolder: '../test-output/viewer-verification/report', open: 'never' }], ['json',{outputFile:'../test-output/viewer-verification/results.json'}]],
  outputDir: '../test-output/viewer-verification/results',
  use: { baseURL: origin, channel: 'msedge', trace: 'retain-on-failure', screenshot: 'on', viewport: { width: 1280, height: 720 } },
  webServer: { command: `"${path.resolve('../.venv/Scripts/python.exe')}" "${path.resolve('../backend/e2e/viewer_server.py')}"`, url: `${origin}/__e2e/health`, reuseExistingServer: false, timeout: 30000 },
});
