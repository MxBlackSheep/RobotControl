# Repeatable inspection viewer verification

These are browser/HTTP end-to-end checks, not unit tests. Read `scenarios.md` and
`database-failure-scenarios.md` for the failure cases recorded before implementation.

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
& ./.venv/Scripts/python.exe build_scripts/pyinstaller_build.py --output-dir dist/viewer-review-20260926
& ./.venv/Scripts/python.exe backend/e2e/packaged_viewer_smoke.py dist/viewer-review-20260926/RobotControl
```

The packaged check copies the candidate into a temporary folder with a different
name, starts it on port 8017 with disposable credentials, automatic recording and
scheduler autostart disabled, and a nonproduction SQL address. It verifies:

- The embedded UI is available and the real logger and browser resolve the same relocated root.
- Startup removes an orphaned reading copy.
- A gzip archive larger than one section is reconstructed through authenticated HTTP.
- Edge can navigate and expand the packaged history reader at desktop and phone widths.
- Released readers leave no decoded temporary files.

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
