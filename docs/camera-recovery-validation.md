# Camera recovery validation — 2026-09-14

## Delivered behavior

One selected camera, saved by DirectShow device identity, owns capture and recording in a supervised Windows process. Recovery is manual. Missing frames are reported after ten seconds (twenty-second startup allowance); repeated images are deliberately not treated as a freeze. Hardware reconnect and viewer reconnect are separate controls.

## Automated and browser checks

- Full backend regression suite: **283 passed**; existing deprecation warnings remain.
- Full configured frontend suite passed **73 tests** before the final request-cleanup addition. Final focused camera tests: **6 passed**, including the added unmount cancellation alongside freshness, identical images, permissions and two refresh cycles.
- A real spawned-process test verifies that a blocked helper is terminated and reaped. Mocked tests cover identity reordering/ambiguity, stale discovery, operation conflicts, first selection while waiting, missing frames, finalized/partial metadata and recording intent.
- An isolated browser fixture verified explicit device refresh, keyboard selection, selection saving, recording-time selection locking and separate camera/recording labels. DOM checks showed no horizontal overflow at 390px and 1280px. The fixture did not operate production data or hardware.
- Production frontend build, resource embedding and isolated Windows PyInstaller onedir packaging succeeded. The final executable served all 22 JavaScript assets with hashes matching the production build; detailed camera status rejected unauthenticated access.

## Short hardware and packaged checks

Windows exposed one **Logi C270 HD WebCam (redirected)**. Source-level isolated recording produced clips, manual reconnect changed generation and resumed recording, and reconnect after an intentional stop remained preview-only.

The first hardware attempt exposed a COM apartment conflict between device enumeration and DirectShow capture. Enumeration now uses the existing COM apartment when appropriate and balances its own initialization. The repeated hardware check succeeded.

The isolated packaged application authenticated against a disposable test account, discovered and selected the camera, recorded, and delivered **11 WebSocket frames in approximately ten seconds**. Manual camera reconnect retained recording intent; stop followed by reconnect supplied preview without recording. Both completed test clips decoded successfully. The application log contained one application startup, and no child processes remained after stopping the camera. The low frame rate is a redirected-camera observation, not an N100 performance claim.

The running previous application was left in place. The candidate contains no test accounts, camera selection, recordings or other validation runtime data.

## Still requiring hardware acceptance

- Physical unplug/replug of the directly attached robot camera and selection among multiple simultaneously attached devices.
- Concurrent viewing over the real remote network while recording, including reconnections.
- Sustained recording, 24-hour screening and longer endurance measurements. The historical freeze occurred after one or two months; these short checks do not prove its root cause or long-term resolution.
- A driver that continues returning repeated images can still appear fresh. This is the chosen behavior; use manual reconnect and diagnostics when an operator notices it.

## Candidate and rollback

Use `dist/RobotControl-camera-recovery/RobotControl.exe` together with its `_internal` directory. The existing `dist/RobotControl` and `dist/RobotControl-optimized` packages are preserved.

For deployment, stop the old application, back up its data directory, then replace application files while keeping that data. Do not run both packages against the same runtime data. To roll back, restore the previous application files with the preserved data. No SQLite migration is introduced.
