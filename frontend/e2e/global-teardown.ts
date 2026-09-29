import fs from 'node:fs/promises';
import path from 'node:path';

export default async function teardown() {
  const manifest = JSON.parse(await fs.readFile(path.resolve('../test-output/viewer-verification/fixture-manifest.json'), 'utf8'));
  await fetch('http://127.0.0.1:8016/__e2e/shutdown', { method: 'POST' });
  // Allow the real server lifespan to release workers/files before Playwright kills its shell.
  for (let attempt = 0; attempt < 100; attempt++) {
    try { await fs.access(manifest.temporary_root); }
    catch { return; }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Fixture cleanup did not complete: ${manifest.temporary_root}`);
}
