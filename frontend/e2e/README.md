# Repeatable frontend design verification

These are browser/HTTP end-to-end checks, not unit tests. Read `scenarios.md` and
`database-failure-scenarios.md`, `ui-redesign-scenarios.md`, `inspection-labware-failure-scenarios.md` and `operations-failure-scenarios.md` for cases recorded before implementation.

## Run on Windows

Use PowerShell from the repository root. The repository's `.venv` must contain
the backend dependencies, and Microsoft Edge must be installed.

```powershell
Set-Location frontend
npm ci
npm run build
npx playwright test
Set-Location ..
```

The harness starts its own fixture server on port 8016. It serves the built UI,
uses the real log routes and reading worker, and supplies synthetic database and
camera data. It does not import the production application or start robot services.
It deletes disposable log files and cache copies when the run ends.

Open `recovery/viewer-verification/report/index.html` for results, screenshots and
browser traces. `fixture-manifest.json` contains expected decoded SHA-256 checksums;
each archived file is reconstructed in both directions and compared with its
checksum. `results.json` contains machine-readable results. This evidence folder
is intentionally Git-ignored; retain it with the release candidate.

## Build and verify a relocated Windows candidate

Choose a fresh output directory. PyInstaller refuses to replace a nonempty
candidate directory; preserve any existing runtime data before building another.

```powershell
& ./.venv/Scripts/python.exe build_scripts/embed_resources.py
& ./.venv/Scripts/python.exe build_scripts/pyinstaller_build.py --output-dir dist/labware-workbench-20260926
& ./.venv/Scripts/python.exe backend/e2e/packaged_viewer_smoke.py dist/labware-workbench-20260926/RobotControl
```

The packaged check copies the candidate into a temporary folder with a different
name, starts it on port 8017 with disposable credentials, automatic recording and
scheduler autostart disabled, and a nonproduction SQL address. It verifies:

- The embedded UI is available and the real logger and browser resolve the same relocated root.
- Startup removes an orphaned reading copy.
- A gzip archive larger than one section is reconstructed through authenticated HTTP.
- Edge can navigate and expand the packaged history reader at desktop and phone widths, switch appearance, and verify default reading height and full-screen phone sizing.
- Released readers leave no decoded temporary files.
- The embedded ten-rack deck retains both carrier columns on desktop and phone,
  using intercepted read-only Labware data; compact connection details omit
  misleading utilization/bandwidth values.

The process and relocated copy are removed afterward. Results are saved in
`packaged-smoke.json`, `packaged-desktop.png`, `packaged-phone.png`, and
`packaged-trace.zip` beside the main browser report. Disposable authentication
tokens in browser traces cease to work after the isolated process exits.

## Coverage and practical limits

The automated matrix includes 1280×720 and 1920×1080, phone widths 320/390, a short
320×390 window, and 844×390 landscape. It checks wide tables, full row values,
SQL finding/copy failure, retained selection and focus, marked camera corners in
4:3/16:9/portrait, crop/zoom/pan, stale/disconnected frames, and stream request counts.
Source-reset checks deliberately hold the no-frame state open to verify camera
keyboard focus. Log checks include UTF-8/UTF-16/Windows-1252, CRLF, oversized lines, gzip/ZIP,
ownership/access/traversal, cancellation, capacity, expiry, source growth and follow.

The redesign adds checks for First/Last/page jumps and failed requests, SQL line
navigation, keyboard rack editing, pending/failed Labware saves, malformed data,
schedule recovery and draft protection, archive phone navigation, Maintenance
unknown state, single-owner monitoring, local storage navigation and System/Light/Dark
appearance. A dark screenshot sweep covers every module and key nested sections.
The log space check requires at least 60% of the 1280×720 window height for text.

The prior viewer-only report is preserved at `recovery/viewer-verification-baseline`.
The main report is the latest complete integrated run.

### Spatial Labware revision

The previous whole-application report is preserved at
`recovery/ui-redesign-20260926-verification`. Rebuild and run
`npx playwright test labware.spec.ts cytomat-spatial.spec.ts system-pages.spec.ts` for the deck selection
and compact connection-details checks, or `npx playwright test` for the full
regression run. The tests record failure scenarios before their production
changes and exercise only disposable intercepted Labware writes.

Check the realistic ten-rack screenshots as well as pass/fail results: Col A and
Col B must remain side by side, and their racks must retain the API order.
The operator-confirmed Cytomat mapping shows positions 1–7 top to bottom; 8–9 are unused. Missing and duplicate rows remain unavailable, and unexpected IDs are preserved separately.

### Native browser zoom (interactive, optional after automated checks)

Run `node frontend/e2e/native-zoom.cjs` from the repository root with port 8016 free.
It starts disposable fixtures and a dedicated Edge window. Set Edge's browser zoom
to 200% (using its menu or Ctrl+Plus) within 3 minutes. The script verifies Find,
horizontal overflow and Back focus, then saves native-zoom screenshots/trace/JSON
and closes both processes. Do not run it alongside Playwright. A viewport-size
check is not a substitute for this native zoom check.

The 26 September automated desktop-control attempt timed out waiting for app access,
so native 200% zoom is not certified by this run. The earlier report preserves its 100% screenshot and incomplete
trace; native zoom remains unverified in this refinement. No actual phone keyboard
or hardware was used.

Camera and database data are fixtures; this does not certify a physical camera,
Hamilton robot, remote network tunnel or production SQL server. Reduced viewport
height exercises the space available with an onscreen keyboard but does not
reproduce an actual phone keyboard. Native browser zoom and real phone keyboards
should also be checked on the VM/phone used by operators.

For VM testing, copy the entire candidate `RobotControl` directory, including
`_internal`, into a new folder. Keep the existing installation and its `data`
directory intact. Open the application and verify tables, procedures, current and
historical logs, and a live camera using the VM's normal setup. Check normal and
200% browser zoom; on a phone, open Find with the keyboard visible, use Back, and
rotate the screen. Fit should retain all image edges; Fill should say Cropped view.

### Rack sizing and selection revision

The preceding spatial report is preserved at `recovery/spatial-labware-20260926-verification`. The current matrix adds 3840×2160, 1366×768, 1024×768/600 and 1920 CSS pixels at 2× device scale. It checks one bulk-selection interaction, Set entire rack, resize cancellation, and responsive geometry. Read `labware-spatial-failure-scenarios.md` and `cytomat-spatial-scenarios.md` for the pre-implementation failure cases. Packaged checks also capture 4K rack scaling and desktop/phone Cytomat order.

### Quiet workbench refinement

The preceding integrated report is preserved at `recovery/labware-layout-20260926-verification`. Read `labware-read-race-scenarios.md` and `labware-layout-stability-scenarios.md` before changing background reads or responsive sizing. Run `npx playwright test labware-layout-stability.spec.ts labware.spec.ts cytomat-spatial.spec.ts` for focused checks, then `npx playwright test` for the final suite. The scenarios cover delayed GET responses arriving after editing begins, stable refresh geometry/focus, static keyboard focus and the connected deck/editor at multiple available widths and heights.