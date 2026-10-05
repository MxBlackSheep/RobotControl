import { defineConfig } from '@playwright/test';
import path from 'node:path';

// E2E_PORT lets two worktrees verify at once; the fixture server reads the same variable.
const origin = `http://127.0.0.1:${process.env.E2E_PORT || 8016}`;

/**
 * Screenshot review for styling and layout changes (AGENTS.md, Verification: "Styling, layout or
 * wording"). It fills every screen with fixed sample data and saves full-page screenshots to
 * test-output/visual/latest for a person to review; it asserts nothing about behaviour.
 *   npx playwright test -c playwright.visual.config.ts            (all screens, light and dark, 1440/1280/390)
 *   VISUAL_ROUTES=/,/labware VISUAL_WIDTHS=1440 VISUAL_MODES=dark npx playwright test -c playwright.visual.config.ts
 */
export default defineConfig({
  testDir: './e2e/visual', timeout: 240000, workers: 1,
  // Same fixture server as the behaviour suite, so the same shutdown removes its temporary logs.
  globalTeardown: './e2e/global-teardown.ts',
  reporter: [['list']],
  outputDir: '../test-output/visual/results',
  use: { baseURL: origin, channel: 'msedge', trace: 'off', screenshot: 'off' },
  webServer: { command: `"${path.resolve('../.venv/Scripts/python.exe')}" "${path.resolve('../backend/e2e/viewer_server.py')}"`, url: `${origin}/__e2e/health`, reuseExistingServer: false, timeout: 30000 },
});
