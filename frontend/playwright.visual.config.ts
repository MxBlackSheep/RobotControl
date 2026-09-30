import { defineConfig } from '@playwright/test';
import path from 'node:path';

/**
 * Screenshot review for styling and layout changes (AGENTS.md, Verification: "Styling, layout or
 * wording"). It fills every screen with fixed sample data and saves full-page screenshots to
 * test-output/visual/latest for a person to review; it asserts nothing about behaviour.
 *   npx playwright test -c playwright.visual.config.ts            (all screens, light and dark, 1440/1280/390)
 *   VISUAL_ROUTES=/,/labware VISUAL_WIDTHS=1440 VISUAL_MODES=dark npx playwright test -c playwright.visual.config.ts
 */
export default defineConfig({
  testDir: './e2e/visual', timeout: 240000, workers: 1,
  reporter: [['list']],
  outputDir: '../test-output/visual/results',
  use: { baseURL: 'http://127.0.0.1:8016', channel: 'msedge', trace: 'off', screenshot: 'off' },
  webServer: { command: `"${path.resolve('../.venv/Scripts/python.exe')}" "${path.resolve('../backend/e2e/viewer_server.py')}"`, url: 'http://127.0.0.1:8016/__e2e/health', reuseExistingServer: false, timeout: 30000 },
});
