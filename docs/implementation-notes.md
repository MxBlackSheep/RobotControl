## 2026-10-05 Overview, System status and Camera live view fit a phone's first screen

- The owner uses an iPhone through the Cloudflare tunnel. Audit at 390×844, 375×667 and 320 px, light and dark: no sideways overflow or nested scrolling on Overview, System status, Camera live view, Labware, Maintenance, Admin, About, Login or the drawer, but the priority pages pushed their answers below the fold. Before, at 375×667 Overview ended in Needs attention (Now running started at y≈631, the strip wrapped to 5 rows); System status's Databases card ("1 cannot connect") started at y≈634 under three 130 px metric cards; the 4:3 live picture shrank to 272×204 with black bars because Fit used only the height left under three rows of controls. Now Overview's strip is a 3-across grid (label above state) and the run is on the first screen even with a hold; CPU/Memory/Disk share one row below 900 px; the live picture runs edge to edge (375×281) with the viewing controls below it, and in landscape fills one screen below the header.
- SQL Server left the Overview strip at the owner's request, with the system-health read that fed only it; System status keeps every connection.
- Touch screens (`theme.ts`, existing `(pointer: coarse), (max-width: 600px)` rule): text fields 16 px (iOS Safari zoomed into the 14 px Login, Maintenance Reason and search fields), section tabs and toggle buttons 44 px. Header text links and the banner's recovery link get a 44 px touch area from a pseudo-element, so bands keep their height. Maintenance's "Last change" moves into the card on phones. Desktop (1280/1440, mouse) is pixel-identical to main except the strip.
- Sign-in: the page focused Username 100 ms after opening, even when Password had already been chosen, so typing (or a fast fill) landed in Username. It now leaves a text field the user chose alone. Found as an intermittent failure of `auth-recovery.spec.ts` (the screenshot showed "operatorsecret" in Username); the case now taps Password first and fails on the old code every time.
- Checks: `system-pages.spec.ts` (Overview first screen at 390×844 with and without a hold, no SQL Server and no system-health read; System status's Databases state on the first screen), `camera.spec.ts` phone case (picture 390 px wide, controls below it), `auth-recovery.spec.ts` (Password keeps focus); full browser suite 127 passed. Screenshots (PR evidence): before/after at 390 and 375, light and dark, plus desktop diffs against main.
## 2026-10-05 Packaged checks choose their port and test only the app they started

- Before, `packaged_viewer_smoke.py` and `packaged_walkthrough.py` always used port 8017 and `packaged_database_smoke.py` 8018. With two worktrees running packaged checks at once, one check could talk to the other's app: 401s, "orphan folder never seen", or a pass earned by someone else's build. Now `PACKAGED_E2E_PORT` sets the port for all three and their browser scripts (`packaged-smoke.cjs`, `packaged-walkthrough.cjs`, which now require it from the launcher). Defaults are unchanged.
- `backend/e2e/packaged_app.py` refuses a port that is already in use, naming the PID and program, and sends no request (not even `/health`) until the listening socket belongs to the process it started. If another process takes the port during startup it refuses as well. It stops only its own process. Identity comes from the socket's owning PID, so no production route was added.
- Checks: candidate `dist/packaged-port-5e03168` (built from 5e03168; the change touches only checks). All three passed on the default ports and with `PACKAGED_E2E_PORT=8027`. With 8017 and 8018 held by a dummy server, all three exited 1 with the refusal message and left the dummy running. The mid-start takeover was exercised directly against `wait_until_serving`. Evidence: `test-output/packaged-port-evidence/`.
## 2026-10-05 Tray shows the app icon with a status dot

- Before, the tray showed a 16 px white square with a coloured circle and a "P". Now it shows the
  RobotControl icon (the frame for the tray's size) with a status dot in the bottom-right corner:
  starting orange, running green, stopped/error red, unknown grey (same colours and meanings).
  The dot is 7/16 of the icon with a dark ring, drawn without anti-aliasing so it stays distinct
  from the white gripper at 16 px.
- Measured: pystray saves the image as ICO and `LoadImage(LR_DEFAULTSIZE)` makes a 32 px handle
  (process DPI-unaware). A 16 px-only ICO is stretched with smoothing (32 of 920 opaque pixels
  equal plain doubling), which also blurred the old icon; a pre-doubled 32 px image loads 920/920
  identical. So when the handle is a whole multiple of the tray size, the tray-size frame is
  pixel-doubled to it; otherwise the handle-size frame is used (125 %/150 % scaling: the shell
  reduces a 32 px design). The shell's reduction at 100 % was not observable on the 200 %
  development PC.
- `RobotControl.ico` is bundled at `build_scripts/icon`; if it cannot be read, the tray keeps the
  old drawn image and logs one warning (ten updates with a missing ICO: one line).
- Checks: status images at 16/24/32 px light and dark, the fallback and the packaged candidate's
  tray (overflow flyout, 200 %) in the PR. No new check: a tray icon failure is not a safety,
  data or scheduling failure. Full browser suite, packaged smoke and walkthrough passed.

## 2026-10-05 Phones: Database, Logs, Scheduling and archive lists scroll with the page

- The owner, on an iPhone through the tunnel, saw about 1.5 rows of `dbo.ActivePlateView` (32 rows), with the OD column cut off at the right edge, and about 2 of 2,072 Python log files in a small box. `InspectionWorkspace` kept a measured height (`70dvh` until measured) on phones too, and the table or list scrolled inside it under its own header, while page chrome took about 40 % of the screen. Now, under 600 px, the workspace has no height of its own: lists and tables scroll with the page. Text readers (SQL, log) keep their own pane (`boundedDetail`), because Follow, Top/Bottom and scroll restore depend on it. At 600 px and wider nothing changes (1440 px screenshots are pixel-identical apart from fixture timestamps and animation timing).
- Database table on phones: the name on one line (tap shows it whole), More, and one search field that applies on Enter or with the search button. Filters, Refresh, Expand table and Page and rows are in More. Rows scroll sideways with the Row column pinned and a right-edge fade while more columns remain. The headings are pinned under the app header (`--app-header-height`, set by `App.tsx`) in a separate strip that follows the rows' sideways scroll and copies widths from an invisible `inert` heading row. A compact paging bar is pinned at the bottom (safe-area inset). 7 rows show on opening at 390×844, and about 10 between the headings and the bar once scrolled at 375×667.
- Logs, archive recordings: `LoadMoreBar` ("50 of 2,000 files", Load more) replaces paging on phones. Logs appends the next API page and lists files that shifted between pages only once. Scheduling's list simply flows. Log sizes read "537 B", not "537.0 B" (`_format_file_size`). The local-only note in `PageHeader` is an info button on phones. `Panel` clips with `overflow: clip` so bars pinned inside it stick to the screen.
- Checks: new phone cases in `database.spec.ts` (390×844, 375×667: rows on screen, no nested vertical scroll, headings pinned and aligned after a sideways swipe, Row column fixed, fade, bar on screen, paging, 320 px overflow), `inspection-pagination.spec.ts` (phone paging and Page and rows) and `logs.spec.ts` (Load more, Refresh, "537 B"). The shared fixtures gained the owner's volumes (`e2e/database-fixture.ts` ActivePlateView, 2,000 files in `viewer_server.py`). The screenshot review gained 375 px, opened views and `VISUAL_SESSION=remote`. `E2E_PORT` lets two worktrees run the fixture at once. Not checked on a real iPhone.

## 2026-10-05 Experiment choices newest first (lookup order setting)

- Before, the Experiment list in Culture history and Delete Experiment was alphabetical by
  UserDefinedID, because `lookup_rows` ordered every lookup by label; an `ORDER BY` in the
  package query is invalid in the derived table it pages. Now a lookup may set `order`
  (`label` default, `label_desc`, `value`, `value_desc`), validated in manifests and Python
  `TOOL` definitions and mapped to fixed SQL (`LOOKUP_ORDER_SQL`); package text never reaches
  the `ORDER BY`. Lookups without it keep label order, and written manifests leave out the
  default, so packages that do not use it stay importable by 0.1.4.
- Culture history and Delete Experiment 1.0.1 use `value_desc` (highest ExperimentID first).
  A manifest cannot declare a minimum app version: 0.1.4 refuses these ZIPs on import
  (`lookup.order: Extra inputs are not permitted`) and keeps 1.0.0. Stated in both CHANGELOGs.
- Checks: `report_wizard_check` (new case: 30 rows, `value_desc` page 1 = 30..6, page 2 = 5..1,
  search, membership from page 2, default label order, unknown order refused via Python and
  ZIP); fails before the change. `tool_authoring_check`, `database_workspace_check`,
  `database_tools_check`, `bundled_tools_check`, `preparation_step_check` pass. Evidence:
  `test-output/lookup-order/`.

## 2026-10-05 Stored clips are denoised in the H.264 conversion

- The owner found recordings "quite noisy, despite the live preview being much better": #51 denoised live view only, and `clip_transcoder.py` stored the camera's noise at 1000 kbit/s. Now the conversion runs `atadenoise` (serial, up to 7 frames, thresholds 0.16/0.32; one filter thread, after the range conversion) from its own setting, `CAMERA_CONFIG.clip_denoise_filter` (`""` stores the noise as recorded). It is wider than live view's 5 frames because a clip has no delay to pay for the held frames; at the same thresholds it removes about 20 % more noise with the same ghosting. `transcode_command()` is the one command the product, `live_view_quality_probe` (`clip:<kbit/s>[:d]` settings, new) and `clip_transcode_probe.ps1` (`product-1000-denoise`, new) share.
- Measured on the owner's clip and two real clips with a moving gripper/arm (development PC): frame-to-frame noise on still areas 5.1–5.5 → 1.1–1.5 (central review's measure on the owner clip: 6.63 stored → 1.11), detail kept 95–97 → 99.5–100 %, ghost on the moving part 0.03–0.08 → 0.06–0.11 (two-frame averaging reads 0.5); no double edges in 2× crops. Size stays at the bitrate (three real clips 7.53–7.95 → 7.51–7.56 MB). CPU about +20 % per clip (1.59 → 1.88 CPU-s, ffmpeg's own time, paired), peak per clip median 1.6 → 2.4 cores (ceiling ≈3) for about 1 s, at BelowNormal: on the 4-core N100 up to about 2.5 cores for 1–2 s a minute (estimate). Not measured on the N100.
- **Evidence trade-off:** stored clips no longer carry raw sensor noise, and a faint change lasting one frame can be softened; recordings converted with the filter stay that way. Decision, tables and how to turn it off: `docs/plans/clip-transcode-denoise.md`, camera maintenance guide.
- Checks: `clip_transcode_check.py` 28/28, 31/31 with `--clips` (filter on) and 31/31 with it off; every clip keeps its sidecar frame count (the filter flushes held frames at end of input). An unknown filter keeps the AVI and reports ffmpeg's message (by hand). Evidence: `test-output/clip-denoise/`.
## 2026-10-05 Alert emails lead with what happened and what to do (HTML and text)

- Before, a silent run log sent "Status: Run Log Inactive", the IDs, "Started at: 2026-10-03T14:02:11.481233", then "Details: … No log activity observed (minutes): 12.4 … Alert threshold (minutes): 10.0", with the attachment notes after the footer. Now the subject is `RobotControl alert: ChamFl_Fluorence – run log silent for 12 min` (prefix kept for mail rules) and the email opens with one sentence: "The Hamilton run log for ChamFl_Fluorence has not updated for 12 minutes (alert after 10). The run may have stopped. Check the robot (camera clip attached) and the run trace." Then Run ("Sat 3 Oct, 14:02 (42 min ago)", "about 60 min", last log, checked, Hamilton status), Attached, a small "For troubleshooting" block (method, trace file, run GUID, schedule and execution IDs, SQL state, unknown context keys) and the footer.
- Every trigger (`log_inactive`, `monitoring_unavailable`, `long_running`, `aborted`, `execution_failed`, unknown) and both manual recovery emails have their own sentence, stating only verified behaviour: an abort mentions paused scheduling only when manual recovery is applied; recovery acknowledged says queued jobs stay paused until Resume queued jobs and the schedule stays inactive. Recovery subjects now share the `RobotControl alert:` prefix (were `RobotControl manual recovery required/cleared:`).
- Mail is multipart/alternative: an HTML part (banner amber for warnings, red for abort/failure/recovery required, neutral for recovery acknowledged; inline styles and tables, ≤ 600 px, every value escaped) and a text part with the same content. One `AlertEmail` (`backend/services/alert_email.py`) renders both; `NotificationLog.message` keeps the text. `send()` gained `html=None`; the SMTP test and manual email stay plain text. Callers, context keys, event types, recipients and attachments are unchanged.
- Checks: `backend.e2e.notification_delivery_check` now reads back what the local mail sink received: both parts with the same facts in order for 8 alert samples and both recovery emails, a hostile experiment name/error/path escaped, unknown trigger and missing fields, the stored record equals the text part, test and manual email single-part text (fails on main: no HTML part). `--render DIR` writes the samples. Test stubs gained `html=`; the rolling-clip note assertion now reads the new wording. Screenshots: Edge light, forced dark and 390 px (PR evidence).

## 2026-10-04 Live view: frames shown evenly by capture time (playout buffer)

- After #54 the owner, watching through the tunnel, found live view "much better", but with occasional frozen frames and then a quick catch-up. Their log (`fps=15 | kbps=403 | keyframes=40 | send_gap_ms_p95=134 | ack_gap_ms_p95=280 | ack_gap_ms_max=612 | hitches=59 | rtt_ms_min=220 | rtt_ms_median=236 | skips=late:0,full:0,…`) shows a full 15 fps with no lag skips and a steady round trip (the link is not queueing). Acknowledgements, sent at decode, come in bursts (p95 280 ms against 67 ms per frame, 59 hitches against 40 keyframes), and the browser showed each frame as soon as it was decoded, so arrival jitter became visible pauses. About 5% of the server's own sends were already ≥ 2 frame intervals apart (`send_gap_ms_p95=134`).
- Now `useLiveViewSocket.ts` holds decoded frames and shows them at capture time + offset + delay: the offset is the minimum (arrival − capture) over 90 frames (clock skew cancels), the delay the p95 jitter above it, clamped 0–300 ms, rising faster than it falls. A late frame is shown at once; only the newest due frame is shown per animation frame; at most 8 are held; pause, resume, reconnect and a new decoder clear it. Acknowledgements stay at decode time. Held frames would pin a hardware decoder's small output pool (a stall freezes live view), so with the buffer live view decodes in software (`hardwareAcceleration: 'prefer-software'`, the default where a browser refuses it): 1 ms a frame median, 2 ms p95, in the check. Off switch: `PLAYOUT_BUFFER = false` (frontend constant, rebuild; default decoder again). Details: camera frontend guide, "Playout buffer".
- Measured in the browser check (Edge, fixture at 15 fps, 4 frames sent together): gaps between drawn frames p50/p95/max 1/264/265 ms before → 67/84/99 ms; frame wait median/max 2/6 → 124/225 ms; all 120 frames in 8 s shown. With 10 frames together (beyond the clamp) waits stay ≤ 319 ms and pauses shorten from 662 to 369 ms. Turned off: 1/266/275 ms, as before. **Cost: expect about +100–250 ms delay on the owner's link in exchange for even motion.** Not measured on the N100, the real tunnel or the owner's browser.
- Checks: new burst case in `camera.spec.ts` (the fixture gained `interval` and `burst`); fails before the change and with the buffer off, and its software-decoding assertion fails on the first revision of this change (default decoder). Evidence: `test-output/live-view-playout/`.

## 2026-10-02 Live view: delivery log per viewer; a far viewer's first picture no longer freezes

- The owner finds live view "a bit laggy" through the tunnel. Each live-view viewer now logs one INFO line per minute and at session end (`Streaming | event=delivery|delivery_end | …`): frames sent, kbit/s, keyframes and their size, gaps between frames sent and between the browser's acknowledgements (p95, max, `hitches` ≥ 2 frame intervals), round trip min/median, window wait avg/max, the window, skips by reason (`late`, `full`, `error`, `replaced`) and frames dropped. Counters only on the frame path. Fields and how to read them: `camera-maintenance-guide.md`, "Live view delivery log".
- Before, a viewer whose first acknowledgement took over about 0.6 s (the first keyframe after the encoder starts is about 30 kB, 13 kB later; e.g. 600 kbit/s 0.3 s away) was skipped to the next keyframe just before it arrived: one picture, then a freeze of a whole GOP. Now waiting frames are judged against 1 s and 16 frames until the first acknowledgement (0.5 s and 8 afterwards, unchanged). Simulated: shown fps 14.2–14.7 → 14.9 in those cases, no start skip on any modelled link from 450 to 1000 kbit/s (one each remain for the light-off model on 500 kbit/s 0.3 s away at GOP 2 and 3).
- `LIVE_STREAMING_CONFIG.keyframe_seconds` (default 1, today's GOP) sets the keyframe interval. Simulated keyframe hitches: one per keyframe on links up to 1000 kbit/s (≈ 60 a minute, gaps of 140–250 ms p95). GOP 2 s halves and 3 s thirds them without shortening them, while joins and skip recovery double (p95 1.0–1.3 → 1.9–2.4 s at 2 s). Kept at 1 s. `performance_probe.py` gained gap p95/max, hitches per minute, skips and their freezes, window waits, `--join-every` and `--keyframe-seconds`. Decision and tables: `docs/plans/live-view-keyframes.md` (development-PC simulation, not the N100 or the real tunnel).
- Checks: `test_frame_delivery.py`, `test_streaming_lifecycle.py`, `test_h264_encoder.py` (every level's keyframes now checked at `settings.gop`). Evidence: `test-output/live-view-keyframes/`.

## 2026-10-02 README rewritten; MIT licence

- The repository was public with no licence. It is now MIT (`LICENSE`, copyright Andy Sun and Shou Group, UCL; `license` in `pyproject.toml`). The bundled ffmpeg keeps its LGPL 3.0 notice in the package's `THIRD_PARTY_NOTICES`.
- `README.md` rewritten for people who install or work on RobotControl: app icon, an Overview screenshot (`docs/images/overview.png`, sample data from the visual review), what each page does, requirements, install and update, the `data` folder, development, tests, packaging and licences. Removed: the printed default admin password (the README now says to set `ROBOTCONTROL_ADMIN_PASSWORD`, and that remote sign-in with the built-in default is refused, #53), the `--layout onefile` advice and the old `dist/RobotControl` output path.

## 2026-10-02 The built-in admin password no longer signs in remotely

- Before, the sign-in page showed every visitor the default admin username and password, which are also in the public repository, and RobotControl is reachable through the Cloudflare tunnel, so anyone with the URL could try them. Now the hint is gone, and while an account still has the built-in password (`BUILT_IN_ADMIN_PASSWORD`, `backend/services/auth.py`) a non-local sign-in (tunnel or LAN, `get_connection_context`) answers 403 "Change the default password on the robot PC before signing in remotely." without tokens or a recorded login. On the RobotControl computer the same sign-in works and opens the existing required change-password dialog (`must_reset` in the login response only; nothing stored).
- "Still the default" is decided at sign-in: the submitted password equals the built-in one and verifies against the account's hash. No schema change or migration, and the rule ends the moment the password changes. A wrong password never reaches the check, so it keeps the same generic 401 whether or not the default is in use. Refused attempts are not counted by the remote throttle, so reading the message does not lock the owner out. A deployment with its own `ROBOTCONTROL_ADMIN_PASSWORD` is unaffected. Hashing, pins, token lifetimes and roles are unchanged.
- Checks: `backend/e2e/auth_storage_check.py` (real SQLite and routes: tunnel, spoofed X-Forwarded-For and LAN refused, local nudge, change then remote success, old password and wrong password identical 401; the new cases fail without the route change). `test_auth.py`'s client is now a loopback peer because its admin step signs in with the built-in password, which is now remote-refused from TestClient's non-IP peer. `auth-recovery.spec.ts` sign-in case: no credentials on the page, the 403 message shown, the local `must_reset` dialog. Evidence: `test-output/default-password-remote/`.

## 2026-10-02 Live view: temporal denoise at 400 kbit/s; camera asked for 30 fps again

- After #48 the owner found live view laggy again over the Cloudflare tunnel, with no less noise. Level 0 was 15 fps at 600 kbit/s, and libopenh264 overshoots in noise (≈840). Now level 0 runs `atadenoise` (serial, 5 frames, thresholds 0.16/0.32; `LIVE_STREAMING_CONFIG.denoise_filter`, `""` turns it off) in the ffmpeg child before encoding, on its yuv420p planes with one filter thread, at **400 kbit/s**. Measured on the development PC with the extended `live_view_quality_probe`: detail kept is above #48's 600k in all five scenes (owner clip 92.6 vs 90.5 %, light-off model 87.7 vs 84.8 %), frame-to-frame noise is about a third, and it sends 406–426 kbit/s even in the light-off model (600k: 846). The moving gripper does not ghost (0.109 vs 0.091 share of the previous frame; averaging two frames reads 0.5).
- Cost: the filter holds back 3 frames, **+200 ms delay** (80 → 284 ms capture to shown on a fast link), so the degraded levels (7.5/300, 5/200) go without it. Simulated tunnel (`performance_probe --kbps/--rtt --clip --level0`, new): on a 500 kbit/s link 600k fell to 11.6 fps and 1.4 s behind (light-off model 7.1 fps, 1.9 s); 400 + denoise kept 14.2 fps and 0.34 s (13.9 fps). Live chain CPU, one viewer: 1.77 → 1.30 % of one core (median); filter alone ≈0.36 ms per frame.
- `capture_fps` is 30 again: the production camera logged `format=YUY2 | requested_fps=15`, then `delivered_fps=30.0`, so #48's 15 fps request saved nothing and its expected "RobotControl N% 5–6 points lower" did not apply (corrected in `live-view-low-light.md` and the camera and performance guides). Decision and figures: `docs/plans/live-view-denoise.md`.
- Checks: camera, live-view and recording tests; a new real-ffmpeg case encodes every configured level (a filter the bundled ffmpeg rejects, or held frames lost or mispaired with capture times, fails it); every level with the filter on and off. Not measured on the N100. Evidence: `test-output/live-view-denoise/`.

## 2026-10-02 Tip tracking no longer offers Reserved or Unclear

- The owner asked to remove the reserved and unclear tip statuses from the frontend only. Before, Set tips to offered seven statuses; now it offers clean, empty, dirty, rinsed and washed. The backend, API and database are unchanged: they still store and report both, and a missing or unrecognised stored value still arrives as unclear.
- A tip saved as reserved or unclear still shows its own colour and name ("Tip 1, reserved"), counts in After saving, and appears in the deck/rack legend only while a shown tip has it, so unknown data never reads as clean. Repainting it saves the chosen allowed status. One named list (`hiddenFromEditing`, `TipTrackingPanel.tsx`) does the hiding; nothing else in the frontend reads tip statuses.
- Checks: new case in `labware.spec.ts` (fails on main: the palette shows Reserved and Unclear); screenshots `test-output/visual/latest/{light,dark}-{1440,390}-labware.png`.

## 2026-10-02 RobotControl.exe and the browser tab show the gripper icon

- Before, RobotControl.exe carried PyInstaller's default icon (floppy disk and Python logo) in Explorer, the taskbar and Task Manager, and `index.html` linked `/vite.svg`, which did not exist, so the tab had no icon. Now both show design B, a gripper carrying a plate. The EXE icon has frames at 16, 20, 24, 32, 40 and 48 px from the simplified art and at 64, 128 and 256 px from the detailed art.
- `build_scripts/icon/` holds the SVG masters, the committed `RobotControl.ico` and `make_icon.py`, which regenerates the ICO and `frontend/src/favicon.svg`. Pillow cannot rasterise SVG, so the frontend's Playwright renders the SVGs with Edge. Packaging only reads the committed `.ico` (`--icon`) and stops if it is missing. At 16 and 24 px the 32-unit art fell on half pixels and blurred, so `icon-16.svg` and `icon-24.svg` are copies of the same shapes snapped to whole pixels.
- The favicon is linked from `/src/favicon.svg`, so Vite emits it as a hashed `/assets/favicon-<hash>.svg`. The packaged server caches every image for a year (`immutable`), so a fixed `/favicon.svg` would keep an old design. A changed design gets a new URL instead.
- Windows caches icons, so an install upgraded in place (same folder) may show the old icon in Explorer, Start or a pinned taskbar shortcut until the cache refreshes. No refresh step was verified. A new `dist/robotcontrol-<commit>` folder is a new path and is not affected.
- Checks: the full browser suite (121 cases; 9 camera cases first failed because this new worktree lacked `build/vendor/ffmpeg`, and passed once it was copied in), packaged viewer smoke and walkthrough on `dist/app-icon-51a7720` (28 pages; the favicon returned 200 on every page). The icons Windows extracts from the packaged EXE at 16, 32 and 256 px are pixel-identical to the ICO frames. Evidence: `test-output/app-icon/`.

## 2026-10-02 Sharper live view in low light: 15 fps capture, 600 kbit/s live view

- Before, the camera was asked for 30 fps while live view used at most 15 and recording 7.5, and live view had 400 kbit/s (≈3.3 kB a frame), which smeared the moving gripper and plate wells once low light raised sensor noise. Now the camera is asked for 15 fps (`CAMERA_CONFIG.capture_fps`; 30 reverts): half the decode and copy work, and in the dark auto-exposure may expose up to 1/15 s instead of adding gain. Live view level 0 is 15 fps at 600 kbit/s (+50 % per viewer in every scene: 610–661 against 407–439 kbit/s lit, 844 against 554 in heavy noise, where libopenh264 overshoots); degraded levels are 7.5/300 and 5/200, which divide 15 so frames stay evenly spaced (GOP `int(fps)`, at most a second).
- Detail kept on still frames (noise-blind measure): lit 88.0 → 89.9 %, real dim 94.2 → 95.7 %; light off, modelled from the lit clip (calibrated shot noise, gain ×8, cyan cast; no real lights-off clip exists) 83.2 → 84.8 % at equal gain and 87.5 % if 15 fps halves the gain. In 2× crops plate well rows stay rows and the moving gripper's fingers no longer merge. Denoise (`atadenoise`) changed detail by −0.3 to +0.1 points at double encoder CPU and was not used; resolution is unchanged. Measurements, crops and decision: `docs/plans/live-view-low-light.md`; repeatable with `backend/scripts/live_view_quality_probe.py`.
- Each connection logs the negotiated format and requested/reported fps, then the delivered fps after 10 s, because a driver may ignore the request. All figures are estimates from the i5 development VM without a camera: chain emulation with a stand-in helper unchanged within noise (11.7 → 11.9 % of one core); `performance_probe` (20 s, helper excluded) 2.4–2.7 → 0.9–2.0 %. Expected on the N100 if the camera delivers 15 fps: System status **RobotControl N%** about 5–6 points lower (helper's per-frame work halved, ≈ −6.4; main −0.3; encoder +0.4 while watched); not observed there. A clip whose camera slowed below the recording rate after connection (frame count ÷ elapsed < 0.8 × fps) now logs a warning that it plays faster than real time; recording is unchanged. Both settings revert from `config.py`.
- Checks: camera, live-view and recording tests; every encoder level against real ffmpeg (keyframes ≤ 1 s, join at a later keyframe decodes); `clip_transcode_check.py`; `performance_probe.py` now schedules its frames at `capture_fps` (fixed sleeps ran its "30 fps" camera at 21 fps on Windows) and moves its scene at a fixed speed per second, so camera rates are compared on the same motion.

## 2026-10-02 RobotControl's own CPU in System status; lighter clip conversion

- The owner saw Task Manager at 86 % on the N100 while System status showed less, and asked whether MP4 conversion is to blame. System status showed only the whole machine's CPU, so nobody could tell RobotControl's part. Now the CPU card's detail reads **RobotControl N%**: the main process and every process it started (camera helper, ffmpeg children, package scripts), as a share of the whole machine over the same 5 s (`health_sampler.py`, `robotcontrol_cpu_percent`; CPU-time deltas keyed by pid and start time). Unknown (first sample, unreadable process tree) shows "RobotControl —", never 0 %. Why Task Manager reads differently (processor utility vs time, 1 s vs 5 s, observers such as Task Manager and remote desktop): performance guide.
- Clip conversion: decoding, filtering and the verifying decode now run with one thread each (`-threads 1` before `-i`, `-filter_threads 1`). Measured with the extended `clip_transcode_probe.ps1` (`product-1000-before` vs `product-1000`) on 8 real 640×480 clips on the development PC (i5-12490F VM, 6 logical CPUs, FFmpeg n9.0.2): 1.50 → 1.24 CPU-s per clip (verifying decode 0.38 → 0.22), peak 1.77 → 1.48 cores, wall 1.26 → 1.56 s, identical output (size, SSIM, frame counts). The expected "one core" was not reached: the MJPEG decoder has no threads, so the encode was never an all-core burst; FFmpeg runs decode and encode side by side, about 1.5 cores. Pinning to one core caps the peak but cost 50 % more CPU-seconds, so it was rejected. The machine-wide peak is not comparable here: the VM ran at 68 % mean from other work before the runs (the probe now records this baseline).
- Checks: `clip_transcode_check.py` (its `ffmpeg_children` helper crashed when a child exited between listing and reading its name, a race in the check; it now skips exited children), sampler against processes' own CPU times (24.5 % vs 24.5 %; a child started mid-window counted from its start), `system-pages.spec.ts` success and incomplete-contract cases, packaged smoke fake, screenshots `test-output/visual/latest/*-system-status.png`. Not measured: the N100. Evidence: `test-output/clip-conversion-cpu/`.

## 2026-10-02 Select EvoYeast experiment 1.0.1: one Experiment choice again

- Before, the schedule's "Before this run" step showed **Experiment** plus **Reset Hamilton tables**, **Tables to reset** and **Reset tables before selecting the experiment**. #40 had copied the retired adapter's `ResetHamiltonTables` token support, which no form in use offered; the original UI was one experiment dropdown saving `ScheduledToRun` + `EvoYeastExperiment:<id>|set`. Now the package has one required input, `experiment_id`: it clears `ScheduledToRun` on every experiment and sets it on the chosen one (same lock, missing/duplicate refusal and rowcount check). A step without an experiment is refused on save (400 "Experiment is required").
- Old tokens: `ScheduledToRun` + one selection still prefills `{experiment_id}`. Any `ResetHamiltonTables` token now gives no prefill and the message "the Hamilton table reset (…) is no longer part of the EvoYeast step", so an administrator decides; the tokens are kept until then and the run is refused before any write.
- Schedules saved with 1.0.0 read Needs review after the update (package hash changed) until an administrator saves them again; importing 1.0.1 is refused while an active schedule uses 1.0.0.
- Checks: `scheduling_lab_check` (reset cases replaced by: required experiment, 1.0.0 inputs refused, `ResetHamiltonTables` token → Needs review without a prefill and resolved by an administrator's save), `preparation_step_check`, `bundled_tools_check`; `scheduling-lab.spec.ts` fixtures. Screenshots: `test-output/scheduling-lab-verification/before-this-run-{light,dark}-{1440,390}.png`.

## 2026-10-02 Starter packages at 1.0.0, release notes in the package, clearer connections

- **Assign connections** (Database settings and Manage packages) was two copies of one dialog, listing "Operation target" before "Connection for primary" (the author's alias). One `AssignConnections` now shows **Reading connection** (read-only accounts) and then, for writing packages, **Writing connection** (operation accounts, same database); an alias is shown only when a package names several. It saves only the declared aliases, as Manage packages did; the Settings copy sent stored mappings unchanged, which the server refuses after an update renames an alias. Check: the new `database-workspace.spec.ts` case.
- Release notes travel with the package: **Publish update** writes the change note as the new version's section at the top of `CHANGELOG.md` when RobotControl builds the ZIP, and **Import package ZIP** prefills **What changed?** from the incoming version's section. Installation history stays local. Download package stays byte-identical to the installed ZIP (schedules pin its SHA-256). Check: `tool_authoring_check.py` (fails without the change at the CHANGELOG assertion).

- Culture history (was 1.0.3) and Delete Experiment (was 1.0.1) are now 1.0.0, like Select EvoYeast experiment. Each starter package has a `CHANGELOG.md`; installing with **What changed?** blank (including first-start seeding, which recorded no message) takes the history message from the CHANGELOG section for that version. History stays per installation; the CHANGELOG travels in the ZIP and its download.
- On an installation that already has 1.0.3 or 1.0.1, importing the 1.0.0 ZIP shows "Install older version"; the calculations are unchanged.
- README: the starter packages need a read-only connection for `primary` (created under **Create read-only account**) and, for Delete Experiment and Select EvoYeast experiment, an operation connection as the **Writing connection**.

## 2026-10-01 Clip storage no longer reports a recovered ffmpeg as missing

- `control-status` → `clip_storage.last_error` kept "ffmpeg.exe is missing" after ffmpeg was available again and clips were converting (found by the central review of #42). That message describes a current condition, so it now clears when ffmpeg is found; a per-clip failure stays reported, because that clip remains MJPEG and is counted in `failed`.
- Check: `clip_transcode_check.py` now asserts the error clears after ffmpeg returns (failed before the fix: idle, 5 transcoded, still "missing"); 31/31 with `--clips`.

## 2026-10-01 System status lists the database connections in use

- The Database card showed only the built-in connection as "EvoYeast · LOCALHOST\HAMILTON · Connection mode primary", left over from when that connection also prepared schedules. RobotControl now depends on the saved workspace connections too (viewer, packages, schedules' before-run steps), and the built-in one still serves Hamilton run records, labware and backup. The **Databases** card lists each connection with its server/database, access, uses and its own state and message; the header is Connected only when every connection is, otherwise a failure count or Partly unknown. An incomplete reply is Unavailable.
- New `GET /api/monitoring/databases` (`DatabaseTools.connection_health`): opens each saved connection as its users do, in parallel. A result under 90 s returns at once and is re-checked in the background after 30 s, so an unreachable server (8 s connect timeout, measured) does not delay CPU, memory or experiments; an older one is re-checked in the request, so failing checks show Partly unknown rather than stale Connected rows. The Overview's "SQL Server" light still reads the built-in connection.
- Checked: `system-pages.spec.ts` (11), type check and build; the endpoint against disposable SQL Server (reachable, missing database, uses, cache); screenshots light/dark at 1440 and 390 px (`test-output/visual/latest/*-system-status.png`).

## 2026-10-01 Rolling clips are stored as H.264

- Before: each 1-minute rolling clip stayed a 640×480 MJPEG AVI of about 45 MB (35–50 MB on real footage; 120 clips ≈ 5.4 GB, a 15-minute archive ≈ 680 MB). Now, once the camera helper has finalized a clip, one ffmpeg child (bundled, libopenh264, 1000 kbit/s, limited-range YUV) re-stores it as `<stem>.mp4` of about 7.2 MB: 4.9–6.6× smaller on 10 real clips, plate and gripper positions as readable as the source at 2× zoom, about 1 s of one core per clip on the development PC (`docs/plans/h264-rolling-clips.md`, `backend/scripts/clip_transcode_probe.ps1`).
- Recording still writes MJPEG, so it never depends on ffmpeg. The MP4 replaces the AVI only after it decodes to the sidecar's frame count, under the clip lock the archive copies under; a missing, crashing or killed ffmpeg or a wrong count keeps the AVI and is reported in `control-status` → `clip_storage`. One child at a time, BelowNormal, in a kill-on-close Job Object (`h264_encoder.find_ffmpeg`, `_kill_on_close_job`). Listing, both cleanups and storage statistics treat the two formats of one clip as one clip; an experiment archive waits up to 60 s for its window's conversion.
- Checks: new `backend/e2e/clip_transcode_check.py` (real ffmpeg, CameraService, archive, cleanup and download on disposable clips; `--clips` adds real footage): 31/31. Existing camera, recording, notification and live-view tests pass. Not measured: the N100 (the probe's header has the command); Windows Media Player playback (Chromium plays the MP4 at its real length).

## 2026-10-01 The EvoYeast flag is a database step

- Before, "Before this run" had two mechanisms: a built-in EvoYeast/batch adapter (radio and experiment list, tokens in `prerequisites`, its own connection chosen under Database settings → Schedule preparation) and the database step from the entry below. Now there is one: the starter package `database_packages/evoyeast-experiment` ("Select EvoYeast experiment") runs the adapter's SQL as an ordinary preparation step (lock the target, refuse a missing or duplicated ID, clear every flag, set one; optional `dbo.ResetHamiltonTables` with the method name and table list, in the saved order). `lab_integration.py`, `lab_settings.py`, the batch-SQLite example, `GET /api/scheduling/lab/preparation`, the `scheduling-settings` routes, the radio and the settings card are removed; the receipt and no-repeat moved to `pre_execution.py`.
- Existing schedules keep their tokens. The owner chose "prefill and needs review": `legacy_preparation.py` derives on every read a Needs review state with the tokens and, where they fit the package, a prefilled step. The run is refused before any write until a local administrator saves the schedule, which clears the tokens; batch, unknown and ambiguous tokens are not guessed. Nothing is rewritten at startup. Clients can no longer send tokens. An administrator's form always sends an explicit step for such a schedule (the prefill, else its saved step, else none), so schedules without a prefill can be resolved too. The owner chose admin-only experiment selection, and to import the package on the existing VM instead of seeding it: each release now ships `starter-packages\<id>.zip` for every starter package beside `RobotControl.exe` (`database_packages/README.md`).
- Found while verifying: (1) the old Schedule preparation settings refused edits to the connection scheduling used; a database step pinned only the connection id, so editing that connection to another database kept armed schedules Ready. Steps now pin server and database too; a change, or a step saved before this, reads Needs review until saved again. (2) A SQL error raised by a step (e.g. the procedure's RAISERROR) reached the receipt as "Cannot use connection …" because `ReportSources.open` relabels driver errors in its block; the receipt now keeps the step's own error. (3) A lookup input set before its control mounted (a saved or prefilled step) showed blank; it now shows its label.
- Checks: `scheduling_lab_check` rewritten for the package and retired tokens (two disposable logins: reader and writer; `ResetLog` records the flag at reset time to prove order), `preparation_step_check` (+ connection edited to another database), `database_workspace_check`, `database_tools_check` (starter set is now three), `bundled_tools_check`, `report_wizard_check`, `tool_authoring_check`; `scheduling-lab.spec.ts` (5), `database-workspace.spec.ts` settings and remote-admin cases, scheduling component tests (33). `packaged_scheduling_lab_smoke.py` tested only the removed adapter and is deleted. Screenshots: `test-output/scheduling-lab-verification/old-selection-*.png`.
- Not verified: the lab's real `ResetHamiltonTables` and a deployed method on the VM.

## 2026-10-01 Camera live view is H.264

- Before: each viewer received JPEG frames (480×360 adaptive, about 160 kB/s on the spike's source), encoded per quality level. Now one ffmpeg child (`backend/services/h264_encoder.py`, libopenh264, 640×480, 15 fps, 400 kbit/s, one-second GOP, no B-frames) encodes once for all viewers, only while someone watches; on the spike's source the same settings used about a quarter of the bytes and CPU. A viewer joins, resumes or catches up at the next keyframe and never queues; a stalled viewer does not slow others. The CPU guard now counts the ffmpeg child and steps the shared stream 15/10/5 fps (400/300/200 kbit/s) and back; the hard stop is unchanged. The JPEG live-view path (`frame_encoder.py`, quality levels, the API's `quality` field, the `<img>` viewer) is removed; snapshots and recordings are unchanged.
- The browser decodes with WebCodecs onto a canvas. Without H.264 WebCodecs (or on a plain-HTTP page, where WebCodecs does not exist) Start is disabled and the reason is shown; there is no fallback (owner decision). Frame header version 2 adds a keyframe flag (`<BIdHHB`).
- ffmpeg runs in a kill-on-close Job Object (a hung encoder cannot outlive a killed RobotControl), is terminated on stop, and a crash shows "Live view stopped unexpectedly and is restarting. Recording is not affected." with a 1–30 s back-off. A missing `ffmpeg.exe` refuses new sessions with 503 and the reason.
- Checks: `test_h264_encoder.py` (real ffmpeg: one-second keyframes, decode from a later keyframe, crash reported once, hung child ended when its parent is killed, input replaced not queued), `test_frame_delivery.py` (one encoder only while watched, keyframe join, lagging viewer skips to the next keyframe while a fast one gets every frame, pause/resume, crash back-off, CPU guard levels, pacing), `camera.spec.ts` against real H.264 from the fixture (decoded corner colours at three frame sizes, unsupported browser and plain-HTTP messages, pause/resume, reconnect, Stop), `packaged_viewer_smoke.py` (the relocated package starts its own ffmpeg only while watched, as its child, and none survives a killed RobotControl). Not measured here: the N100 with the real camera beside a running method (commands in the PR).

## 2026-10-01 Packages include ffmpeg for H.264 live view

- The owner chose H.264 as the only live-view encoding, encoded by a bundled LGPL ffmpeg.exe (brief, licence position and decisions: `docs/plans/h264-live-view-spike.md`). `build_scripts/fetch_ffmpeg.py` downloads one pinned BtbN build (n9.0.2-17, release branch 9.0), checks its SHA-256 and caches it in `build/vendor`; the package build runs it first and puts `ffmpeg.exe` beside `RobotControl.exe` with `THIRD_PARTY_NOTICES` (LGPL 3.0, OpenH264 BSD, build and source). About names the component. The package grows by 134 MB, which the owner accepted.
- Nothing runs ffmpeg until the H.264 live-view change. The README now describes remote access through the Cloudflare tunnel only; ZeroTier over plain HTTP is no longer used.

## 2026-10-01 SQL Server checks no longer leave logins behind

- Every `database_workspace_check` run left its `rc_report_check_<id>_reader` login on `.\HAMILTON` while still passing. Its cleanup ran `DROP USER …; USE master; DROP LOGIN …` as one batch while pooled connections still held the login. `DROP LOGIN` failed, and pyodbc reports an error from a later statement in a batch only on `nextset()`, so nothing raised. `tool_authoring_check` created its `_writer` login before the `try` that removed it.
- `report_wizard_check.sql_fixture` now removes every login named after its own UUID login (`<login>_<role>`). It ends each login's sessions first and runs one statement per call, so a failure raises. The per-check login cleanup in those two checks and in `packaged_database_smoke --wizard` (its `_packaged` login) is gone.
- Checked: `database_workspace_check`, `tool_authoring_check`, `report_wizard_check` and `preparation_step_check` pass with no `rc_report_check_%` database or login added. A forced failure with a live extra-login session also leaves nothing. A killed process still leaves its fixture behind (one pair from `tool_authoring_check`, 2026-10-01 04:59).

## 2026-10-01 Packaged database check uses a real report connection

- `packaged_database_smoke` stopped with 409 "Connection setup needed" before generating culture history (seen on the `camera-live-view-b7027e0` and `database-preparation-fa8d0c4` candidates). Its uploaded fixture package swapped the server's database and report sources in module-level code. That ran only while installation imported packages, which ended in 10bf346, and reports now run in a spawned process that the swap could not reach. The product was right; the check was stale.
- The check now saves a read-only connection to a disposable `.\HAMILTON` copy of the `DatabaseFixture` rows and assigns it to each package through the administrator routes. The fixture package proves activation by running its report. The default run therefore needs local SQL Server, like `--wizard`. The check also runs when started by file path.
- Evidence: `test-output/packaged-smoke-cbc6771/{default,report-package,wizard}/packaged-results.json` on candidate `dist/packaged-smoke-cbc6771`.

## 2026-10-01 A database step before a scheduled run

- Database packages gain a third kind, **preparation**: `prepare(context, inputs)` that runs unattended before a scheduled method starts. Before, only the two built-in lab adapters ran before a run, and their module stated that no uploaded Python ever would.
- A local administrator picks the step and its inputs under **Before this run** in the schedule form; the server pins the package file hash, version and operation connection. Other roles see it read-only and cannot attach, change or remove it; their timing edits keep it.
- At dispatch, after the adapter step and under the same `LabPreparation` receipt, the step runs in a spawned process with a two-minute limit, SERIALIZABLE with XACT_ABORT, committing only after it returns, and holding no scheduler lock. Raise: rolled back, receipt `failed`. Timeout or crash: `unknown`. Both stop the launch and request recovery; neither is retried. A changed or missing package, or a rebound connection, blocks the run before any write until an administrator saves the schedule; updating, removing or rebinding a package an active schedule uses is refused.
- Authoring: preparation tools install as a package ZIP (`database_packages/examples/preparation`, CONTRACT.md); the **Add tool** page has no safe trial run for them yet. The page redesign is deferred until the parallel database PRs settle.
- Checks: new `backend/e2e/preparation_step_check.py` against disposable SQL Server (permissions and pinning; commit with run context and no repeat; raise/hang/crash; update/remove/rebind refusal and needs-review blocking), `scheduling-lab.spec.ts` (timing edits never send the step; read-only for non-admins; administrator change sent; rejected save keeps it). The browser check found the schedule list dropped the new fields (`normalizeSchedule`); fixed. Existing `scheduling_lab_check`, `database_tools_check`, `tool_authoring_check`, `bundled_tools_check`, `database_workspace_check` pass.
- Limit: `DatabaseTools` asks the scheduling database which active schedules use a package (read-only); checks that construct `DatabaseTools` read the local scheduling database for that.

## 2026-10-01 Camera live view: no cropping, steadier stream over the tunnel

- Fill kept the Fit height while widening the image, hiding 19–39 % of the frame (measured at 1920×1080 down to 1024×768). It is now **Width** ("Fit width"): the whole frame at full width, the page or dialog scrolls; only zoom crops. The expanded "fullscreen" view never measured the dialog (its content mounts through a portal one render later) and kept the page's size; it now fills the screen. A server resolution drop no longer flips the viewer back to Fit.
- Frames were base64 JPEG in JSON, pushed as fast as encoded: on a slow tunnel they queued, delay grew, and one send over 5 s ended the session, which then stayed stopped and blank. Frames are now binary (25 % smaller), acknowledged by the browser with at most two in flight (frame rate follows the link, delay stays bounded, no encoding for frames a viewer cannot take), paused while the tab is hidden, and reconnected automatically with the last image kept as stale. The CPU guard's quality reduction now recovers after 10 calm seconds; its thresholds and hard stop are unchanged. The requested quality was ignored (query vs body) and is now read.
- Checks: `camera.spec.ts` (whole frame in Fit width and expanded, mode kept, acknowledgements, pause/resume, automatic reconnect, no reconnect after Stop), `test_frame_delivery.py` (two in flight, silent viewer released, pause, CPU guard sequence). `backend/scripts/performance_probe.py` speaks the new protocol (1 viewer ≈13 of 15 fps with immediate acknowledgements; a second viewer shares the encode).
- Not measured: frame rate, bytes/s and delay on the N100 through the Cloudflare tunnel with the real camera. Capture (640×480) and MJPEG AVI recording are unchanged. H.264 via ffmpeg is a separate spike (`docs/plans`).

## 2026-10-01 Remote use through the Cloudflare tunnel

- Before, a Cloudflare challenge page (HTML 403) during refresh deleted the saved sign-in, and the login page said "Invalid username or password" for any failure, including an unreachable server. Now only RobotControl's own 401/403 ends a sign-in, and `services/requestError.ts` classifies failures (offline, unreachable, timeout, proxy page, local-only, app) for messages: login titles connection failures "Connection problem"; `requestMessage` no longer says "Check the fields" for a dropped connection. A failed profile read after a password change no longer signs the user out.
- The status bar says "Connection to RobotControl lost · retrying" (or "This device is offline") while the latest request got no RobotControl answer; the `api` interceptors own that state, no new poller.
- Backup creation used the 10 s default against a 300 s server bound, so a normal backup reported "timed out" while it continued (also locally). It now waits 330 s. Backups are local-only, so no tunnel is in between; a background job was not needed. A dropped connection during restore says "Restore outcome unknown" (never "failed", never retried).
- A missing hashed chunk (old page after an upgrade) got `index.html` with 200 in the packaged app, so the page failed to parse and the app went blank. It now gets 404 (as development mode already did); `loadComponent` reloads once when `/health` answers, then `PageLoadBoundary` offers Reload with the shell intact.
- The packaged app no longer publishes `/docs`, `/redoc`, `/openapi.json`, source maps or `bundle-analysis.html` (opt-in with `SOURCEMAP=1` / `npm run bundle-analyze`). Remote sign-in is throttled (5 per username, 20 per address, 5 minutes; local never throttled; tunnelled guesses with a spoofed `X-Forwarded-For: 127.0.0.1` are throttled because of the classification fix below). Pages name sections that need the RobotControl computer. Returning to a tab or regaining the network refreshes polls at once; hidden tabs keep their policy.
- Not changed, with reasons: Scheduling's 30 s status interval (requests time out at 10 s and replies are ordered by safety revision, so it cannot overlap); GZip (Cloudflare compresses for browsers; measure CPU first); sliding refresh tokens (needs server logout first).
- Checks: `auth-recovery.spec.ts` (proxy 403 keeps the sign-in; sign-in errors; both fail on the previous code), `database-restore.spec.ts` (unknown outcome, one request), `database-workspace.spec.ts` (remote administrator), `auth_storage_check.py` (throttle, local exemption, outage not counted), packaged smoke (hidden docs/maps, missing asset 404). Setup guide: `docs/maintenance/backend/remote-access-guide.md`.

## 2026-10-01 Tunnelled requests are never local

- Before: a loopback peer was local whenever the *first* `X-Forwarded-For` entry was loopback. A tunnel on the RobotControl computer (cloudflared) connects from loopback and Cloudflare appends the real client after whatever the client sent, so a remote request with `X-Forwarded-For: 127.0.0.1` gained local access (package upload, restore, schedule writes). Reproduced: the new case fails on the previous code with 200 on a local-administrator route.
- Now a loopback peer is local only without proxy headers (`cf-connecting-ip`, `cf-ray`, `true-client-ip`, `x-real-ip`, `forwarded`) and with only loopback `X-Forwarded-For` entries. The recorded `client_ip` is the proxy-reported address (Cloudflare header, else the last `X-Forwarded-For` entry), not the client-supplied first one. Access only narrows; remote use through the tunnel keeps the same local-only limits as before.
- Checks: `backend/e2e/database_tools_check.py` (seven tunnelled header variants refused, loopback-only chains allowed) and `backend/e2e/auth_storage_check.py` (sign-in reports `is_local=false` when tunnelled). 109 related unit tests pass. Not verified on the N100: whether cloudflared there connects from loopback (it does when the tunnel's service URL is `localhost`).

## 2026-10-01 Laboratory settings and camera selection survive a scanner reading the file

- The WinError 5 replace failure from the entry below also applied to `scheduling-lab.json` (Apply and Cancel change overwrite it) and `data/config/camera_selection.json` (every reselection overwrites it). Both now use `utils/filesystem.replace_file`. Holding either file open with all sharing modes made the previous code fail at once with `PermissionError: [WinError 5]`; the new code replaces it. No retry was added.
- Unchanged on purpose: the camera worker's sidecar and `.partial.avi` → `.avi` moves, and log relocation into `history`. Clip names carry a microsecond timestamp and the connection generation, and log relocation picks a free name first, so they never replace an existing file and a scanner on the source does not block either call.
- Checked with `backend.e2e.draft_replace_check`, `backend.e2e.database_workspace_check` (Apply and Cancel over an existing file) and the camera tests from the camera guide.

## 2026-10-01 Draft Try no longer fails when another program has the draft open

- `tool_authoring_check` failed about 1 run in 4 with `PermissionError: [WinError 5]` while Try replaced `report-drafts/<key>.json`. No RobotControl thread or the report worker held the file: every draft read already takes `authoring.lock` and the worker inherits no handles. A single-thread write-and-replace loop failed 24 of 5,000 times, with no holder left by the time it was queried. A short-lived outside opener (antivirus or indexer) was opening the new file. `os.replace` (MoveFileEx) refuses to replace a target while any other handle is open, even one that allows deletion.
- `utils/filesystem.replace_file` renames with POSIX semantics (`FileRenameInfoEx`), which replaces the target while such handles stay valid: 0 failures in 20,000 replaces. It is still atomic, and falls back to `os.replace` only on volumes without that call. Report drafts, the package index and saved connections use it. No retry was added.
- New `backend.e2e.draft_replace_check` holds the draft open as a scanner does; it failed on the old code and passes now. A holder that forbids deletion still gets a clear error and leaves the old draft intact.

## 2026-10-01 Report wizard SQL check matches the current draft and publish contract

- `backend.e2e.report_wizard_check` had failed since `10bf346`; the product was right both times. A saved draft has been stored as the full `ReportDraft` (`model_dump()`) since `fc22455`, so once `10bf346` added fields the check does not send, GET returned them with defaults (`tool_id`, `entrypoint`, later `kind`, `files`, `change_note`…) for ones the client omitted; the wizard round-trips that whole object, and installed-tool edits depend on it. The check now compares against the sent draft over the model defaults, still whole-object equality.
- Since `5aed710` publishing retires the draft and an identical repeat returns the installed result without another history event (lost-response retry). The check's second install was such a repeat yet expected 409. It now asserts the repeat changes nothing, and keeps stale-update coverage with a second draft installed against a stale hash (409, package and history unchanged), then installs that draft and replays the first publish, which must be refused (409) with the newer version still active. Disabling either guard makes the check fail.
- Real SQL Server `.\HAMILTON` run passed with fixtures removed (`test-output/report-wizard-verification/sql-http-results.json`). No product code changed.

## 2026-10-01 Database tools check matches no-import installation

- `backend/e2e/database_tools_check.py` still expected a package that fails on import to be rejected at install (400). Since `10bf346` installation deliberately does not import package Python in the server, so that package installs. The check now proves the current contract: the import failure ends that report run, the server keeps answering and a following good update reports again. Sections after that point had never run on `main`.
- Since reports moved to a child process (`10bf346`), every exception from package code was shown as the headline report error with no Details. The worker now tells the server whether it was a `ValueError`: those stay the message (for example a stale choice); others show "Report generation failed" with the text under Details, as before `10bf346`.
- The check now also expects a fault to refuse a new operation preview (preview takes the change guard since `10bf346`), and its two-report hold holds the server-side job instead of a patch the spawned worker never saw.

## 2026-10-01 Overview at narrow widths (Codex review)

- At 900px (collapsed rail, ~388px half panels) Recent runs showed no experiment names and Up next truncated them; strip states overlapped the next label and were clipped on 320px phones; Latest experiment hid its times below 900px and squeezed the method name at 900px. Rows now follow the panel's width (`@container`, as Users and Database do), strip cells wrap by content, and Latest experiment puts its details below the name when narrow.
- The screenshot runner now uses the suite's `global-teardown.ts`; before, each run left a `viewer-e2e-*` folder (large fixture logs) in `%TEMP%`. The runner's sample data now includes a Latest experiment with an end time.
- Verified by screenshot review (light/dark, 320/390/900/1280/1440px, plus worst-case strip states) and the Overview behaviour check. Presentation only: requests, Retry and accessible names unchanged.
- Second review (`e2a4271`): Up next's 104px time column clipped "Tue 20 Oct 11:00" at 900px (and on phones before). It is 128px at every width, enough for the longest `dayTime` ("13 Jan 2027 09:00"); compact rows drop the duration instead. The Scheduling list's date columns had a 120px minimum and wrapped that label; now 128px. The screenshot fixture adds a next-year schedule.
- Hand-over on `dist/redesign-candidate-6` (built from `e2a4271`): 51 component tests, 109 browser checks, packaged smoke and 28-page walkthrough passed (`test-output/redesign-candidate-6-verification.json`). Not exercised: hardware, SQL Server, camera.

## 2026-10-01 Design system A: one system for every screen

- Approved direction A ("instrument console", mock: https://claude.ai/artifact/ApKjN7njdXXfQpZ1RDqRhx), light and dark. Tokens on a 4px unit and the primitives `PageGrid`, `Panel`, `ListRow`, `StatusDot` in `PageLayout.tsx`; every screen moved onto them (`a3db127`, `4faf47e`, `0d45d4b`). Overview, Maintenance and Labware follow the mock exactly.
- Labware: the After saving summary sat on an extra footer line, so the first edit made the shared row taller and moved both diagrams (reported by the owner). The footer is now one fixed line.
- Checks changed because they described the old layout: Labware geometry expects the 12px gutter between the two panels; the Overview strip label is "SQL Server"; Maintenance rows are found by name instead of MUI's Stack class (`35c6067`); the packaged Cytomat gap allows the 24px page padding (`de8f49a`). The Maintenance Reason panel's region is "Maintenance details", so it no longer shares the field's name.
- Verification is tiered (AGENTS.md): styling by screenshot review (`playwright.visual.config.ts`), the full suite and packaged checks once at hand-over: 51 component tests, 109 browser checks, packaged smoke and walkthrough passed on `dist/redesign-candidate-5` (`test-output/redesign-candidate-5-verification.json`). Not exercised: hardware, SQL Server, camera.
- Deviation from the mock: the Labware deck keeps the 40/60 split and 320px minimum (protects 44px tip targets), so its edge is at 40% rather than exactly on a grid column.

## 2026-09-30 Design pass: page edge, card alignment and use of space (`c7797a0`)

- All screens share one left edge (`PageContent` no longer centres); Overview has a three-column layout from 1500px of content width. System status service cards use the resource cards' columns. Camera's Recent recordings fills the right column on wide screens. History is one card with the shared `columnHeading` style. Dates use `dayTime` everywhere, with the year for other years.
- Presentation only: no handler, request, permission or accessible name changed. A review subagent checked the diff and before/after screenshots; its findings (year in dates, Labware keyboard order, 320px camera buttons, 600-900px System status, Overview row length at 1920px) were fixed.
- Checks: all 109 browser checks and 51 component tests pass. Not done: a visual pass against real schedules and the local SQL Server (the preview start was not permitted in this session).

## 2026-09-30 Align Overview card rows and heading baselines

- Corrects the independent column stacks introduced below: Up next / Instrument health and Recent runs / Latest experiment now share row tracks and stretch to their taller card. Recovery uses the same column boundary; the phone layout retains recovery priority.
- Panel headers reserve a 36px minimum height so headings align whether or not they contain an action button. Content can still grow and wrap.
- Build and 19 existing browser checks passed. Light/dark visual probes measure card edges and heading baselines with populated, empty and held states, including the 1000px workspace breakpoint. Evidence and source/build hashes: `test-output/overview-alignment/verification.json`. No hardware or Windows package verification.

## 2026-09-30 Align frontend composition and panel presentation

- Page titles and actions now share a consistent row above section tabs. Dashboard pages stop at 1440px; task forms at 1120px. Tables, logs, camera and labware retain their available working width. Normal panels use 8px corners and 16/24px insets; panel headings share `PanelHeader`, with spacing owned by the parent.
- Overview stacks upcoming and recent activity together beside instrument health and the latest experiment, removing the empty row under a short upcoming list. Maintenance's heading, Refresh and form share the same bounded width.
- Scheduling groups runtime status separately from the collection, with explicit Refresh queue / Refresh schedules labels. Restore uses flat source tabs, Refresh beside the selector, compact filename display, a single selection summary and separated actions. Validity indicators, expandable metadata, permissions, drafts and confirmations remain intact.
- Production build and all 109 existing browser checks passed without weakening assertions; three focused Maintenance cases passed again after a final label-width correction. Visual evidence and build identity are retained in `test-output/appearance-consistency/verification.json`; the repeatable probe uses the isolated viewer fixture and existing schedule/backup fixtures. No new permanent presentation-only tests. Real hardware, production SQL, native browser zoom and a new Windows package were not exercised.

## 2026-09-30 Correct maintenance holds and elapsed time after redesign review

- Maintenance's Right now panel reports Scheduled runs as Held while maintenance or recovery is active. Unavailable or pending maintenance reads and failed robot reads show Unknown; a stopped scheduler shows Stopped. Refresh preserves the operator's reason draft.
- New run observations save the launch time with a UTC offset. The queue API qualifies older server-local launch times before returning them, so Overview and Maintenance agree across browser time zones. Missing or invalid starts remain unknown. Old timestamps in the repeated autumn hour cannot identify their original offset, and assume the original server timezone.
- Verification and review evidence: `test-output/maintenance-review-fix/verification.json`, `test-output/timezone-review-fix/verification.json`, and `test-output/review-fixes-final/verification.json`. Hardware, SQL Server and packaged execution were not exercised.

## 2026-09-30 Redesign step 8: review findings, Overview from the mock, remaining gaps

- Review P1/P2 (`f689ccd`): the shared robot status read recovery only from the queue reply, so a newer recovery in the scheduler reply was hidden from the rail and tab; it also ignored `resume_required`, so the warning cleared while queued jobs still waited for Resume. `newerRecovery` now keeps the higher `safety_revision` (unhealthy storage always wins) and `robotAttention` includes the Resume hold. A new check reproduces both and failed against the old behaviour.
- Overview (`e508fdc`, `697f2d1`): running jobs now report `experiment_path`, `estimated_duration` and the monitor's `launched_at`. Overview has the mock's Now running, Needs attention, Up next, Instrument health and Recent runs panels. Elapsed time is shown against the user's estimate; past it the bar stops claiming progress and says how far past. The always-on status bar is replaced by a banner shown only when runs are held or status cannot be read; phones get a slim header with the menu button.
- Status colours (`50e6350`): History's running is blue and archived recovery amber, via one execution-status mapping.
- Mock gaps: Scheduling table with status filters and a 400px details panel (`ec75936`); Labware status and tip-family buttons and an after-saving summary (`3f37025`); Camera Live view first, Recording and Camera cards, recent recordings (`b9c01d4`); Logs compact file-list header (`db0ef0f`); Admin accounts table (`b3f9c96`); System status Database and Live view cards instead of a disclosure (`a822315`); Maintenance Right now panel and running-HxRun note (`06bdb1c`); shared headings, empty states and labelled Refresh (`e651270`).
- Checks changed because they asserted the old layout: the appearance shell check asserts navigation instead of the removed bar; Labware checks press the status and family buttons instead of choosing from menus; System status checks assert the facts in their cards instead of a collapsed disclosure. What they verify is unchanged.
- Found while verifying: after adding filter buttons, Back from schedule details on a phone focused the "All" filter (also `.Mui-selected`) instead of the open schedule; `InspectionWorkspace` now prefers `aria-current`.
- Verification: backend scheduler and monitor tests 43 passed; 51 component tests; full browser suite 108 passed. Evidence: `test-output/redesign-step8/verification.json`. Not exercised: real hardware, scheduler, SQL Server and camera.

## 2026-09-30 Redesign step 7: remaining screens brought to the approved mock

- Camera (`524e0d6`): at 1200px and wider the camera and recording controls and live-view details sit beside the image; narrower screens keep them collapsible below it. The archive's folders and recordings are card panels with monospace filenames.
- Database (`7a3a843`, `437f800`): monospace table names and cell values; each table shows its data state, with "Could not check" in amber. MUI `h6`, the panel heading used app-wide, is now 16px so the page title is the only large heading.
- Logs (`599bb5f`): file list and reader as card panels with monospace filenames.
- Maintenance (`ca5ed64`) and Admin (`497aef3`) leave the narrow centred column for the normal page width; the maintenance card is capped at 880px. System Status (`874af8f`): large monospace figures on the resource cards.
- Not changed, deliberately: Labware's tip-family selector stays a dropdown (the mock's segmented toggle would change a control its checks and layout rules depend on), and the schedule editor form (not drawn in the mock) only takes the theme.
- Checks: full browser suite 106 passed and 51 component tests passed, with no check changed in this step. Evidence: `test-output/redesign-step7/`.

## 2026-09-30 Redesign step 6: module titles and final verification

- Camera and Admin headings are now the module name ("Camera", "Admin"); the section is shown by the selected tab, as on every other module. The storage-health check in `system-pages.spec.ts` now asserts the selected "Storage health" tab instead of a heading of that name, because the title no longer names the section.
- Found by the full suite: four `auth-recovery.spec.ts` cases failed because the collapsed rail (the default below 1440px) showed only the account initial. The old header always showed who was signed in. The collapsed rail now shows the name and role as a tooltip and keeps them as screen-reader text; expanded and phone views show them as before.
- Full verification: type check, 51 component tests, full browser suite 106 passed. Evidence: `test-output/redesign-final/verification.json`. Not exercised: real scheduler, SQL Server, camera hardware, a packaged Windows build and native browser zoom.

## 2026-09-30 Redesign step 5: shared status labels on the remaining screens

- Camera ("My view"), Maintenance ("HxRun launches"), System Status (freshness, database, live view) and Database Restore (file type, Valid/Invalid) use `StatusChip` with unchanged text. Blocked for maintenance is amber; Invalid and Database disconnected are red. Logs had no status chips and needed no change.
- `StatusChip` now shrinks with an ellipsis like the MUI Chip it replaces, and shows the full label as a tooltip.
- Found while verifying: "monitoring has one refresh owner…" failed 4 of 8 runs. A diagnostic showed the step-1 status bar's "Live" marker 5px past a 320px screen in the frame after resizing, while the rail was still 64px wide: "Scheduler running" could not shrink. It now ellipsizes; the same check then passed 12 of 12, and the diagnostic found no overflow in 18 runs.
- Checks: `camera`, `database-restore`, `database`, `appearance`, `system-pages` specs (32 passed).

## 2026-09-30 Redesign step 4: Labware

- The existing layout already matches the approved structure (packed physical deck beside a full-width editor with 44px tips) and picks up the shell and theme from step 1. Only the "Read only" chips (tips and Cytomat) move to `StatusChip`, and the Col A/Col B labels take the mock's small-caps style (DOM text unchanged).
- Not adopted from the mock: the pinned unsaved-changes bar. `labware-layout-stability.spec.ts` requires that adding or clearing unsaved tips never moves either diagram, and a bar that appears on edit would. Save, Undo and Discard stay in the toolbar.
- Checks: `labware.spec.ts`, `labware-layout-stability.spec.ts`, `cytomat-spatial.spec.ts` (39 passed, unchanged). Native zoom (`labware-native-zoom.cjs`) was not rerun; no sizes changed.

## 2026-09-30 Redesign step 3: Scheduling

- Restyle only; every label, permission, recovery gate, confirmation and the `safety_revision` ordering are unchanged. The schedule list shows the method path and a status chip per row; the detail panel has a header with name, chip and path; the calendar lists each day's runs as rows; notification delivery statuses use the shared tones. "Recovery required" is amber everywhere (it was red in the list and outlined red in the summary).
- `StatusChip` falls back to the light tones outside the app theme; without it, three `RecoverySafetyPanel` component tests (rendered without the app theme) crashed.
- Checks: `operations.spec.ts`, `scheduling-lab.spec.ts` and the scheduling component tests pass without changes. Evidence: `test-output/redesign-step3/`.

## 2026-09-30 Redesign step 2: Overview

- Scope for the rest of the redesign is refactor only: new look and shared patterns, no new features, nothing removed (recorded in the plan).
- Dashboard is renamed Overview (sidebar, title, Alt+1). The Latest Experiment card keeps its content, 60 s refresh and Refresh button. Before, a failed refresh replaced the card with an error; now the last good experiment stays on screen with "Showing data from HH:MM:SS". Its timer moved from `setInterval` to `useSerialPolling`, so a slow earlier reply can no longer overwrite a newer one; the 1 s start delay (waiting for sign-in) is gone because the shell now renders only after sign-in.
- Verified with a temporary fake-clock browser run (failed state, error after data, recovery on the timer, first-load error, no experiments); not kept as a permanent check (read-only card). Evidence: `test-output/redesign-step2/`.

## 2026-09-30 Redesign step 1: app shell

- Brief and approved mock: `docs/plans/2026-09-30-frontend-redesign.md`. Branch `redesign/instrument-panel`.
- Every page now shows the robot's state in a status bar: scheduler running/stopped, the current run, and a link when a run needs recovery (before, recovery was only flagged while Scheduling was open). A failed read keeps the last known recovery and says how old it is; with no good read the bar says "Status unavailable", never "Scheduler running".
- The sidebar is a dark module rail with the account menu and Appearance at its foot; About moved into the account menu. Sections moved from the sidebar into tabs in `PageHeader`, built from the same permission rules. Breadcrumbs and `SchedulingNavigationContext` are removed.
- Theme tokens (`palette.rail`, `palette.tone`) and `StatusChip`; IBM Plex is bundled with `@fontsource` so offline PCs render the same.
- Found while building: `SchedulerServiceResponse` declared a `status` string, but the backend returns an `is_running` boolean. The type now matches the backend.
- Checks: new status-bar case in `system-pages.spec.ts`; the dark all-module shell check now also asserts the status bar. Three sidebar section-menu unit cases were removed with the menus; the remaining navigation cases moved to `navigation.test.tsx`. Evidence: `test-output/redesign-step1/verification.json`.

## 2026-09-30 Error-handling audit fixes (#16–#20)

- #16: a sign-in storage error (for example SQLite `database is locked`) now answers 503 from `/me`, protected routes and `/api/auth/refresh`, so the browser keeps its tokens; bad, expired, wrong-type and revoked tokens still answer 401. Request timeouts keep the Axios error and say "Request timed out" instead of blaming the database. The 503 maintenance-overlay part landed in #15. Check: `backend/e2e/auth_storage_check.py` (3 of 13 cases failed before the fix).
- #17: Scheduling queue and scheduler status reads each own an inline error that clears on their next success; a failed poll no longer opens the "Server Error" dialog, and a schedule reload no longer hides it. Recovery state is ordered by the server's `safety_revision` (review follow-up: request order had discarded a delayed answer carrying a newer revision); unhealthy storage is always shown. Checks: `frontend/e2e/operations.spec.ts` (status error, older/newer revisions in both response orders, and unhealthy storage). A second review found that later requests still bypassed the revision check; they now obey it too. Request order only breaks revision ties; reopening Scheduling resets history after a deliberate store restore. Evidence: `test-output/pr22-ready/verification.json`.
- #18: the dashboard "Latest Experiment" card keeps its refresh timer after an error and clears the error on the next success, so it recovers without a manual Refresh. Verified with a temporary fake-clock browser run (failed on the old build, passed after); screenshots in `test-output/error-audit-verification/issue-18/`.
- #19: Camera and System Status requests use the shared client, so an expired sign-in is renewed instead of failing with 401 forever; recording downloads renew once on 401. Camera errors have one owner each, so a recordings load no longer clears a live-view error (which then no longer appears as an archive dialog), a failed live-view status read shows "unavailable" with Retry, and a proxy HTML error shows "Camera operation failed (502)". Monitoring keeps an unknown start time as `null`. Checks: one case each in `camera.spec.ts` and `system-pages.spec.ts` (both failed before the fix); the other items were verified with a temporary browser run, screenshots in `test-output/error-audit-verification/issue-19/`.
- #20: a table whose data check fails is listed as "Could not check" (`has_data: null`) instead of "Empty", and `]` in a table name is escaped. The unused `DatabaseService.execute_stored_procedure` (unescaped `EXEC [name]`; its routes already answer 410) and its two unit tests are removed. Screenshot: `test-output/error-audit-verification/issue-20/`.

## 2026-09-30 Keep essential coverage while trimming test duplication

- The suite now requires a concrete essential failure and no equivalent retained coverage, rather than a fixed success/failure quota per screen. Routine presentation, internal-state copies and recoverable read-only browsing are removed.
- Browser cases decrease from 132 to 97. Restore is consolidated from 13 cases to 3: failure feedback/retry, a slow restore with completion warnings, and backup selection under stale replies/new drafts. The real SQL check cannot cover browser timeouts or selection races. Layout matrices retain phone/desktop/4K plus the short 1024px labware boundary; focus animation is checked once using the normal motion setting.
- Five component-test files remain deleted. Of the two others, only four checks remain: bounded complete exports/cancellation and explicit robot/cleanup-method confirmation/cancellation. Recording checks decrease from 37 to 9, retaining disabled startup, cancellation, failed camera start and complete start/stop behavior. The camera fixture now reaches the intended failed-start path, and startup cleanup runs while dependencies are still mocked.
- The shortcut check now waits for the authenticated page and uses an available camera-status fixture so a maintenance modal does not intercept its keys. Review caught an Edge `ERR_NO_BUFFER_SPACE` failure loading React; the isolated retry passes without changing application code. Original failure traces are preserved.
- Verification is focused on the changed checks; no application code, dependency or build inputs changed. The prior full run and fresh focused commands/results are distinguished in `test-output/pr14-review/verification.json`.

## 2026-09-29 Preserve the next directory path while browsing

- A completed directory request no longer replaces a different path typed while it was pending. The loaded directory still uses the server's resolved path; Enter/Go submits the retained draft.
- Added the reproduced failure and subsequent navigation to `frontend/e2e/database-restore.spec.ts`. Final branch verification and merge review: `test-output/restore-merge-ready/verification.json`; the original failing probe remains in `test-output/restore-merge-review/`.

## 2026-09-29 Repair restore browsing and retain sign-in during outages

- The `.bck` browser consumes the real response envelope, loads typed paths on Enter/Go, ignores stale responses, clears old selections and preserves drive roots. Restore results say completed and retain server warnings; the backup button now names the managed `.bak` it creates.
- Both restore paths share SQL execution and recovery, starting in `master`. Backup creation reuses the command runner. Removed unreachable timeout handlers, obsolete package import fallbacks, unused compatibility model copies/imports and frontend debug logging.
- Saved sign-in survives temporary `/me` and token-refresh failures. The app waits for verification and retries; rejected credentials still return to login. A late refresh cannot undo logout. A 503 from `/me` no longer starts the 60-second maintenance window, which had blocked the recovered page (the server-failure browser check failed 3 of 4 runs).
- Review follow-ups: the `.bck` browser shows the server's resolved path, so Parent Directory works after a path typed with `/`; folder errors show the server's reason from the standard error body; failed restores and failed single-user recovery are logged at ERROR.
- The original 140-pass/168-error backend run was caused by access denied to the existing pytest temporary directory. A fresh workspace `--basetemp` allows all 308 tests to pass. Browser fixtures cover recovery, rejected credentials, restore failure/success/warnings and directory navigation; the SQL E2E check restores only a disposable database, including connections starting inside the target database and simulated timeout recovery. Commands, build identity, outcomes and screenshots: `test-output/restore-session-review/verification.json`.
- No executable candidate was requested or rebuilt; this verifies source and the production frontend build, not packaged deployment or robot hardware.

## 2026-09-29 Allow slow restore responses without losing failure feedback

- PR #12's 660-second restore request timeout is combined with PR #10's response success check and PR #11's shared status dialog. Other API timeouts remain unchanged.
- Resolved the overlapping restore spec into one suite, retaining failure/retry cases and checking both success and failure after a 12-second response delay. Evidence: `test-output/restore-timeout-verification/verification.json` and `report/index.html`. This verifies browser behavior with synthetic responses, not an eleven-minute or real SQL restore.

## 2026-09-29 Restore failures use the current dialog API

- PR #10 now incorporates current main, including PR #11's shared `StatusDialog`. HTTP 200 with `success: false` shows the restore error without activating maintenance or clearing the confirmation. The obsolete `showStatusDialog` call is replaced with `setStatus`.
- The `.bck` browser check verifies PR #11's inline selected path instead of dismissing a removed popup. Focused verification: `frontend/e2e/database-restore.spec.ts`; evidence and repeatable commands: `test-output/database-restore-verification/verification.json`.

## 2026-09-29 Restore from a `.bck` path works

- Database Restore → `.bck` (`POST /api/admin/backup/restore` with `file_path`) failed on every request: `BackupService.restore_backup_from_path` called `_get_database_connection`, which only `SqlCommandExecutor` defined. It now runs `SQL_RESTORE_TEMPLATE` through sqlcmd with `RESTORE_TIMEOUT` under the operation lock, like managed-file restore, and sets `MULTI_USER` again if SQL Server rejects the file. Both results now carry a message. The unused `_get_database_connection` wrapper is removed; `open_restore_connection` stays for connection recovery.
- Not changed: a failed restore still returns HTTP 200 with `success: false`, and `DatabaseRestore.tsx` shows "Restore Started" for any 200.
- Check: `backend.e2e.backup_restore_check` now also covers `.bck` path restore with an open session, invalid paths rejected before SQL, and an unrestorable `.bck`. Evidence: `test-output/backup-restore-verification/results.json`.
- Merge review: the check now saves its report even when SQL authentication or cleanup fails, closes its held connection on exceptional exits, and records uncommitted changes alongside the commit identity. The restricted-process authentication failure is retained in `test-output/backup-restore-verification/authentication-failure.json`.

## 2026-09-29 Database and scheduling guides rewritten by topic

- `docs/maintenance/backend/database-maintenance-guide.md`, `backend/scheduling-maintenance-guide.md` and `frontend/database-frontend-maintenance-guide.md` are now single current-state guides (files, behavior, permissions and safety gates, checks, troubleshooting) without dated sections. Each claim was checked against the code on `main`; commands and the package contract are linked to `frontend/e2e/README.md`, `database_packages/` and the SQLite safety guide instead of repeated.
- Corrected: the worker has seven dispatch gates, not three; backup restore does not take the scheduler's `database_change_guard`; `SQL_BACKUP_PATH` is resolved but unused (SQL Server writes to `LOCAL_BACKUP_PATH`); `DatabaseService` does not use the shared connection manager; the Database viewer is chosen on the server, not per browser; the table catalogue has no Important-only filter.
- Removed: "how to extend" and merge-checklist sections, `/api/database` health endpoints and ad-hoc query tasks that no longer exist, `_ensure_schema`, `test_scheduling_pipeline.py`, and one-off verification history. Documentation only; no build or browser run.
- Reconciled with the duplicate-code cleanup on `main`: retained both change records, documented direct restore connectivity checks, narrowed the backup locking guarantee, and distinguished Restore visibility from local-only API access. The guide explicitly records the existing broken path-restore call rather than presenting it as a working alternative. Verification: source and Markdown-link review; no executable changes.

## 2026-09-29 One dialog, one loading indicator, one SQL connection builder

- Action results use one `StatusDialog` on MUI's Dialog. Removed `ErrorAlert` (with six wrappers), `Modal`, `useModalFocus` and `Modal.md`, which re-implemented MUI's focus trap. Before, restore and backup messages opened as a second dialog over the restore screen, and a failed backup showed its error twice; now they appear inline. The unreachable non-admin branch of `AdminPage` is gone (the router already redirects).
- `LoadingSpinner` keeps only the spinner and progress bar callers use; buttons use `CircularProgress`. The shortcut list lives only in `useKeyboardNavigation`, and the help dialog renders it. Escape no longer clicks the first control labelled "close" on the page; the SQL Find field closes itself on Escape, as before.
- SQL Server connection strings come from `build_connection_string` (`backend/utils/odbc_driver.py`). Labware and Cytomat share `labware_connection.py`; the four copies of the default config are gone. The unused 433-line pool/circuit breaker (`backend/core/database_connection.py`) is replaced by `open_restore_connection` in `backup.py`, keeping its two logins. Dead code in `backup.py` removed (a shadowed duplicate exception class, an unread performance monitor, an `import config` fallback). Connection strings are identical before and after: `test-output/duplicate-removal/connection-strings.json`, produced by `compare_connection_strings.py` beside it.
- Docs: rewrote the main-application, authentication and scheduling frontend guides by topic (stale sections on `tabItems`, Jest suites, hypothetical extensions and History using `useScheduling` removed; a contradictory copy of the navigation rules dropped). Folded dated fragments into the camera and monitoring guides, merged the browser guide's three database sections into one table, and reordered `CONTRACT.md`.
- Checks: frontend build; Vitest 78 passed; backend pytest 308 passed; full Playwright suite 112 passed, including new cases for the result dialog (Retry/Close/focus), inline restore messages, shortcuts/help and Escape in Find. Not rebuilt as an executable.

## 2026-09-29 Code review cleanup toward 0.1.5

- Backups use one folder: removed the `SQL_BACKUP_PATH` setting (left over from remote-VM development and never used), so SQL Server and RobotControl both use `LOCAL_BACKUP_PATH`, default `<app root>/data/backups`. `.env.example` no longer points at the old VM share. Restores now get the 10-minute `RESTORE_TIMEOUT` instead of the 5-minute backup limit. Check: `backend/e2e/backup_restore_check.py` (disposable SQL Server database).

- Polling owners recover from a request that never responds: a 20-second deadline aborts it, shows "Request timed out" and retries. Before, a held System Status response left Refresh disabled and the page "connected" indefinitely. Check: `frontend/e2e/status-stall-probe.py`.
- Removed code nothing reaches: about 17,400 frontend lines (unrouted pages, hooks, utilities, five never-run Jest suites, unused packages, unconfigured ESLint) and about 8,800 backend lines (six dead modules including the unused job queue, monitoring WebSockets and the System Config API that wrote secrets to `.env`, ~40 endpoints with no caller). `/recovery/require` stays as an admin safety control. The frontend build now fails on unused locals.
- Fixed restore from a `.bck` path, which always failed with NameError.
- Tests: stale backend and unit tests updated (backend 308, unit 78 pass). Nine browser cases for package authoring, the report wizard and tool authoring no longer matched the screens and were removed; those screens now have HTTP/packaged checks only.
- Version 0.1.5 in `backend/version.py`, `pyproject.toml` and `package.json`; no tag until release confirmation.
- Repository tidy-up: test evidence moves from `recovery/` to `test-output/` (earlier entries still name `recovery/`; that evidence was deleted). Removed the unverified Docker recipe, the two build wrapper scripts, the unused `requests` dependency, and the old lab scheduling-database copies. The build writes its `.spec` and temporary files under `build/`; pytest no longer creates `.pytest_cache`.
- Failure cases moved from ten `frontend/e2e/*scenarios*.md` files into the header comment of the spec or backend check that covers them; superseded revisions (for example fitted-card Labware sizing) were dropped. `frontend/e2e/scenarios.md` is now the single work-in-progress list. `AGENTS.md` and `CLAUDE.md` are no longer tracked by Git.
- Newcomer cleanup: README and the documentation map no longer link to the untracked `AGENTS.md`; the README layout now lists `database_packages/` and the test folders. Removed the finished response-format migration guide, an empty `backend/data/experiment_cache.json` the app never reads (it caches under the root `data/`), and ignore rules for files that no longer exist.
- Git workflow: new `CONTRIBUTING.md` sets branch naming, pull-request-only changes to `main`, verb-first titles and lowercase `v` tags. Deleted the stale `Refactor/CodeOptimization` branch (its last commit was already on `main` as `cb68e18`) and `backup/2026-09-29` (fully contained in `main`). Old tags `V0.1.1`–`V0.1.4` keep their names; lowercase copies were not added because Windows clones cannot hold tags differing only in case. Earlier commit messages were left unchanged, since rewriting published history would break existing clones and links.
- Verification: `backend/e2e/packaged_walkthrough.py` opens all 28 pages of the packaged executable. Still open: operation scripts holding scheduler locks, restores not checking for an active run, and hardware acceptance. See `docs/release-readiness-review-2026-09-29.md`.

## 2026-09-28 Tool replacement, publication completion and history

- Replace Python now replaces the defining script even when renamed, preserving helpers. Supporting uploads reject a second tool definition. Input guidance points to `TOOL['inputs']`; installed rows use Excel report/Database operation labels and one Edit action. Global ZIP import remains the alternate update path.
- Publishing returns to the installed list with a versioned success message and retires its draft. Atomic publication receipts prevent duplicate updates after lost responses. Optional notes persist in unfinished drafts; History records version, timestamp, publisher, note and file changes for Python and ZIP publications, without claiming source rollback or reconstructing old history.
- Focused real SQL/HTTP and desktop/phone checks cover replacement, failed updates, restart persistence, completed-draft removal and lost-response retry. Repeat commands, screenshots and candidate evidence: `recovery/tool-publishing-verification/index.html`. No new unit tests; unrelated working edits preserved.

## 2026-09-28 Existing database tools as single Python files

- Converted Culture history and Delete Experiment to `culture_history.py` and `delete_experiment.py`, with literal `TOOL` definitions and searchable experiment inputs. Function bodies are unchanged; bundled manifests now target those sources. Existing installations update through Edit → Replace all files → Try → Publish update, without rebuilding RobotControl.
- Focused HTTP checks preserved both installed identities, compared complete workbook values/formatting against `5e9b4ff`, and checked deletion preview, typed confirmation, rollback and duplicate execution with disposable data. Repeat command and evidence: `recovery/bundled-tools-verification/index.html`. No application/frontend changes or new unit tests.

## 2026-09-28 Python-defined reports and operations

- Manage packages now has one Add tool workflow: upload prepared Python, choose connections, try, then enable. A small `TOOL` definition produces the form; imports identify bundled libraries, and RobotControl builds versions/manifests/ZIPs. Authors still adapt their calculations; Python is trusted code, not sandboxed.
- Reports generate downloadable Excel; operation trials call only preview under launch protection and rollback, with no execution token. Enabling checks the current draft, trial result, connection revision and explicit review. Existing Operations confirmation and execution remain separate.
- Edit report/operation preserves identity and supporting files, supports complete file replacement, and keeps the installed version until publication. Old drafts and package ZIPs remain supported. Activation journals recover interrupted connection assignment.
- Focused real SQL/HTTP and desktop/phone browser checks, workbook evidence and repeat commands: `recovery/tool-authoring-verification/index.html`. Relocated Windows candidate results are recorded there. No new unit tests.

## 2026-09-28 Simpler database setup and installed report editing

- Tables and Stored procedures now use one admin-selected, server-persisted viewer database. Schedule preparation shows the active setup before editing; the existing connection is visible and ordinary EvoYeast selection no longer requires optional ResetHamiltonTables.
- Edit report retains installed Python, inputs, mappings, sibling tools and supporting files, suggests a patch version and publishes without manual JSON/ZIP editing. Changed installation bases are rejected. The choice builder can filter by an earlier answer; operations support the same read-only lookup sources and revalidate selections before execution.
- Reports run in separate five-minute processes; activation no longer imports uploaded code. Previews share launch protection, roll back, and use a consistent catalogue/source lock order. Python remains trusted code, not sandboxed.
- Focused SQL/HTTP, desktop/phone workflows and product review: `recovery/database-simplification-verification/index.html`. Process crash/timeout, stale choices, rollback, draft preservation and settings recovery checked; no new unit tests. Candidate verification is recorded alongside the evidence.

## 2026-09-28 Portable package editing and reviewed database settings

- Added installed-package ZIP downloads and report editing downloads containing the original Python, configured handler, inputs and concise editing instructions. Report/operation selectors stay visible; package rows identify both kinds.
- Added local-admin Database settings for connection uses, package assignments and the existing scheduling integrations. Scheduling changes are reviewed, blocked by work/recovery/active schedules, and saved for restart with cancellation; active and pending connection profiles cannot be changed underneath them.
- Clarified read-only account review and kept its actions visible. Certificate trust stays explicit and is remembered only for the same server after a successful save.
- Focused disposable SQL/HTTP and desktop/phone browser checks, product-review corrections, repeat commands and Windows candidate evidence: `recovery/database-settings-verification/index.html`. Existing preparation algorithms and bindings remain unchanged; no new unit tests.

## 2026-09-28 Report discard, release contents and inherited SQL execution

- Added confirmed Discard and close alongside Save and close in report authoring. Fresh reports leave no draft; saved drafts use existing ownership/running checks, failures retain work, and installed packages remain untouched.
- Replaced broad pandas/openpyxl collection with standard runtime hooks and explicit test-suite exclusions. The prior candidate contained 1,122 pandas test modules. The packaged check now inspects release contents and generates Excel through pandas/openpyxl.
- New read-only SQL identities explicitly deny database EXECUTE, including public diagram-procedure grants. Verification stays strict; failed post-creation cleanup closes only the new login's pooled sessions. Earlier orphaned identities still require administrator review.
- Failure scenarios, disposable SQL/browser checks, retained dialog failure trace and separate Windows candidate results: `recovery/report-release-verification/index.html`. No new unit tests; actual VM permissions remain a deployment check.

## 2026-09-28 Read-only account setup diagnostics

- Replaced the generic SQL setup error with specific name-conflict, sign-in, authority, database and driver guidance. Unknown failures retain stage/numeric diagnostics without exposing SQL or passwords; existing logins remain untouched.
- Clarified new-login versus administrator identity and the manual SQL versus Create account paths. Failed setup retains connection fields while clearing administrator credentials.
- Focused disposable SQL/HTTP and desktop/phone browser checks passed. Fixed owned SQL fixture cleanup for pooled sessions; retained the original cleanup failure. Commands, screenshots and Windows candidate results: `recovery/database-access-verification/index.html`. The original VM failure's cause remains unconfirmed.

## 2026-09-28 Scheduling laboratory integrations

- Kept native scheduler SQLite and Hamilton run monitoring separate from laboratory preparation. EvoYeast remains the default; existing schedule tokens and unrelated preparation steps survive editing. A reviewed built-in SQLite batch example demonstrates another schema, with per-installation configuration and concise Experiment/Batch controls.
- Added captured installation/execution identities and original schedule-to-database bindings. Missing records, unavailable databases and unsupported preparation now block launch; transaction-owned flag changes roll back. Duplicate execution IDs are not prepared again after restart. Changed targets cannot redirect old schedules or unfinished work.
- Verified disposable SQL Server preparation/rollback, HTTP choices, restart/target protection, separate SQLite batch preparation and desktop/phone editor workflows. Existing safety/executor checks passed; 12 other selected legacy checks fail identically against the prior commit (documented in the maintenance guide). Replaced obsolete placeholder pipeline unit checks with focused integration coverage; no new unit tests.
- The local schedule store was empty: reference behavior comes from existing code/form, not a captured live run. A supervised deployed-method comparison is still required before hardware use. Setup/examples: `backend/services/scheduling/examples/README.md`. Repeat commands, screenshots, useful failures and Windows candidate verification: `recovery/scheduling-lab-verification/`.

## 2026-09-28 Configurable Database workspace and simpler report creation

- Added named SQL Server connections for table/procedure viewers and explicit writable targets for operations. Schema-qualified browsing supports other labs without requiring RobotControl tables. Operation reviews capture the connection/version and reject changes; native scheduler, labware, monitoring and Restore connections remain separate. Existing operations need a target assignment once.
- Database connections now offers reviewed creation of a new read-only account or existing-account setup. One-off SQL authority is discarded; new credentials are encrypted locally. Existing logins are never altered and failed setup rolls back/cleans up its new identity.
- Create report starts with Upload Python or a no-database example. Ordinary/nested imports are detected without execution; package bookkeeping is under Details and compatible scripts skip the starter. Python calculations remain author-owned. SQL Server is supported; external SQLite remains deferred.
- Focused SQL/HTTP checks, legacy scheduler/deletion/workbook checks and desktop/phone browser workflows passed. The product specialist accepted the screenshots. No new unit tests. Commands, fixture identities, useful failure traces, screenshots and Windows candidate verification are retained under `recovery/database-workspace-verification/index.html`; current author instructions are in `database_packages/README.md`.

## 2026-09-28 Saved report wizard and read-only SQL sources

- Added Create report with saved private drafts, original/handler separation, starter download and edited-handler upload, trial Excel, package export and reviewed installation. Python calculations remain author-owned; multiple reports use the existing chooser. The product specialist reviewed desktop/phone screenshots and draft/result handling.
- Report connections use dedicated SQL Server accounts, encrypted local credentials and package source aliases. Effective permissions are checked on connection, including cross-database grants; no writer fallback. Existing reports need a primary source assignment. Added typed dates and searchable dependent database choices with server-side membership checks. Operations and Culture history calculations remain unchanged.
- Focused browser/HTTP workflows, real SQL Server 2008 read/write-denial checks, legacy workbook parity and operation safety checks passed. No new unit tests. Commands, fixture identities, failure traces, screenshots and separate relocated Windows candidate results: `recovery/report-wizard-verification/index.html`. See `database_packages/README.md` for the shorter wizard-first authoring guide.

## 2026-09-28 Restore Culture history reference behavior (1.0.2)

- Removed the 1.0.1 missing-well rejection, which incorrectly changed Data.py's sorting/first-N culture selection. Explicit SQL NULL-to-string conversion preserves the original legacy pandas behavior under bundled pandas 3; no culture-ID pattern is special-cased.
- Compared complete workbook values/formatting with the original script for an extra culture 98500000 on plate 985 and selected/ancestral missing wells. HTTP checks and upload/run in the existing relocated executable passed. No frontend/executable rebuild or new unit tests. Package: `dist/package-updates/culture-history-1.0.2.zip`; commands, fixture identity and results: `recovery/culture-history-verification/index.html`. Actual VM data remain unexamined.
- Replaced the mixed authoring/reference README with one four-step example and exact prompt answers; moved interface/limits to `database_packages/CONTRACT.md`. The product specialist reviewed the revised guide. Installation is unchanged.

## 2026-09-28 Database authoring, reviewed updates and task workspace

- Added a product-specialist workflow for new/unclear features. Package authors keep ownership of Python; the scaffold preserves the original script, generates an adapter/agent brief and builds a versioned ZIP without executing it. See `database_packages/README.md`.
- Package installation now offers non-executing inspection, explicit Update and installed/incoming versions. Reviewed hashes protect against intervening changes. Operations/retrieval use a full-width experiment/task workspace with retained phone Back state.
- Culture history 1.0.1 handles missing well labels under pandas 3 without dropping selected cultures; ambiguous subset selection identifies the plate/cultures instead of guessing. Deliver its ZIP separately because executable upgrades do not replace installed packages.
- Focused authoring/HTTP checks and desktop/phone browser workflows passed; the product specialist reviewed screenshots. Initial browser failure was a wrong test locator, retained with its trace. No new unit tests. Repeat commands, candidate identity and packaged outcome are in `recovery/database-verification/index.html`. Candidate: `dist/database-authoring-20260928/RobotControl`. Actual experiment 333 and SQL Server/ODBC remain VM checks.

## 2026-09-27 — Portable database packages and delivery logs

- Added local-admin ZIP package management, shared operation/report forms, guarded Delete Experiment and private Excel generation using the bundled runtime. Retired public raw SQL/procedure execution.
- Pinned culture-history calculations to upstream ed676fbe3b113329b7748935c87f6d3219743cb5; fixed duplicate OD-column selection without changing calculation rules.
- Recorded manual/test/recovery deliveries, added visible log refresh and partial/unknown outcomes, and prevented retries caused only by logging failure.
- Focused HTTP/SMTP/browser evidence: `recovery/database-verification`; package contract: `database_packages/README.md`. SQL Server/procedure and hardware compatibility remain VM checks; verification uses disposable database rows.

## 2026-09-27 Proportionate engineering and clearer guidance

- Reviewed testing, communication and code structure. Tracked `AGENTS.md` now defines requirement-first design, justified abstractions, verification matched to impact, release-only packaging and concrete user-facing explanations. Retired the standing frontend specialist workflow.
- Replaced the browser run guide's release history with focused commands, corrected blanket testing instructions, added a documentation map and retained the review in `docs/engineering-review-2026-09-27.md`. Playwright now retains traces on failure by default; full traces remain available with `--trace on`. Existing tests, screenshots and release artifacts are preserved.
- Checked local documentation links, diff formatting and Playwright configuration discovery (100 existing cases). No browser tests or application build were needed; the previous release report is unchanged.

## 2026-09-27 Adaptive full-workspace Labware sizing

- Removed desktop width caps and fitted-size ceilings. Tip tracking uses a 40/60 overview/editor split when minimum controls fit, shared diagram bounds, adaptive spacing and circular dots. Smaller windows retain focused rack viewing and usable minimum targets.
- Cytomat fills available width/height with nine equal base rows, one desktop register scroll area and normal compact-page flow. Inline editors, long values and unexpected positions remain reachable. Shared external measurement avoids child-size feedback; refresh, selection and draft safeguards remain.
- Verification: all 100 integrated browser checks and native 200% Edge zoom passed. Two frontend specialists independently reviewed corrected desktop/phone screenshots. Frontend build, embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-adaptive-20260927/RobotControl`; repeat commands, initial failure traces, final HTML results, native-zoom evidence and checksums: `recovery/viewer-verification`. The packaged archive assertion now allows 20 seconds for a real 1 MiB section; its first five-second timeout and successful retry are retained. Actual phones and physical equipment remain VM/operator checks.

## 2026-09-26 Quiet Labware workbench and stable refresh

- Applied the selected A direction as a layout refinement: a joined deck/rack surface, aligned bounded heading/actions, quieter tip wells and a compact Cytomat shelf register with one inline editor. Width and height fitting retain the physical layout and readable phone targets.
- Background reads use fixed-space status text instead of moving progress bars or repeatedly disabling controls. Static keyboard focus replaces the pulsing tip ripple. Starting an edit synchronously invalidates an unfinished read before React pauses polling; draft, Undo and Save safeguards remain.

- Verification: all 92 integrated browser checks passed; two specialists reviewed the final desktop/phone screenshots. Frontend build, resource embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-workbench-20260926/RobotControl`; repeat commands, HTML reports, screenshots, traces and hashes: `recovery/viewer-verification`. Disposable fixtures/processes were removed. Native zoom, actual phones and physical equipment remain VM checks.

## 2026-09-26 Labware visual alternatives awaiting selection

- Prepared three isolated interactive concepts for Tip tracking and Cytomat: Quiet workbench, Rack tray and Deck first. Two frontend specialists reviewed the alternatives and investigated reported flashing. Production integration and packaging wait for the user's visual choice.
- Browser recordings confirm a 12px background-refresh layout jump, disabled-control flicker/focus loss and MUI's repeating focus ripple. A synthetic 503 also opens the global maintenance overlay; this is not established as the user's incident. Complete blanking was not reproduced across 1,078 frames at the normal refresh cadence.
- Preview captures, browser checks, source identification and reproducible flashing traces are retained in `recovery/labware-concepts-20260926`; start with `flashing-findings.md`. The editable conversation preview is `C:/Users/Hamilton/.codex/visualizations/2026/09/26/01a0dca6-5c7b-7110-98b3-4cf4d9271115/labware-design-options.html`. No production frontend or backend files changed.

## 2026-09-26 Responsive tip selection and Cytomat shelves

- Sized the selected tip rack to both available width and height, with scalable dots/labels, a bounded workspace for 4K displays and readable minimum targets on short screens. Replaced Paint/Rectangle modes and row/column/range tools with Set tips to, block selection and Set entire rack; Undo and batch Save remain.
- Applied the operator-confirmed Cytomat order: positions 1–7 from top to bottom, with 8–9 marked Unused and noneditable. Plate assignments sit beside their shelves. Missing/duplicate positions remain unavailable; unexpected IDs retain their exact names separately.
- Two frontend specialists independently reviewed geometry, input behavior and screenshots across desktop/high-DPI/phone sizes. Their cross-review also identified and corrected stable dropdown naming and selection across horizontally scrolled phone columns. Updated the repeatable browser scenarios and Labware maintenance guide; no unit tests added.

- Verification: all 76 integrated browser checks passed, including native touch selection across offscreen columns. The regression was reproduced before the fix and passed afterward. Frontend build, resource embedding, Windows compilation and relocated-package checks passed. Candidate: `dist/labware-layout-20260926/RobotControl`; repeat commands, HTML reports, screenshots, traces and checksums: `recovery/viewer-verification`. Temporary fixtures/processes were removed. Native browser zoom, actual phones and physical equipment remain VM checks.

## 2026-09-26 Physical tip deck and clearer System Status

- Restored the two-carrier tip overview in backend rack order, with all rack patterns visible and an enlarged editor for state-first click/tap and rectangular painting. Undo, cancellation, batch Save and failed-save drafts preserve deliberate control; phone Back returns to the same deck selection. Two frontend specialists reviewed geometry and interaction behavior against the original layout and professional deck-map patterns.
- Replaced System Status's two technical cards with one compact Connection details disclosure. Database errors remain visible; live-view session capacity no longer appears alongside ambiguous bandwidth/utilization measures.
- The Cytomat API contains position names but no physical rack/shelf mapping. A matching physical map awaits the operator's mapping; existing Cytomat reading/editing remains available. See `docs/labware-spatial-review-2026-09-26.md`.
- Verification: all 58 integrated browser checks passed, plus a focused touch-editor screenshot rerun with animations completed. Frontend build, resource embedding and PyInstaller succeeded; the relocated candidate passed embedded deck/status, real log-root, archive checksum and cleanup checks. Candidate: `dist/spatial-labware-20260926/RobotControl`; reports, screenshots, traces and checksums: `recovery/viewer-verification`. Fixtures and temporary processes were removed. Physical equipment mapping, native zoom and actual-phone behavior remain VM/operator checks.

## 2026-09-26 Unified responsive frontend and appearance

- Added persistent System/Light/Dark appearance, compact shared page patterns, keyboard-resizable inspection selectors and readable phone navigation. Logs now use one reader toolbar with Find on demand and folder controls inside the selector.
- Added table First/Last/page jumps with correct retained-data labels after failures; SQL Top/Bottom/line navigation; focused rack/Cytomat editors with keyboard/touch access, protected pending saves and recoverable malformed-data errors.
- Scheduling now uses a retained list/detail workspace, compact queue/recovery controls and protected phone editor drafts. Camera archives use responsive bounded lists; live frame/session behavior is preserved. Two frontend specialists cross-reviewed both scopes.
- Maintenance treats unknown/failed state explicitly and preserves edited reasons. System Status has one polling owner and distinguishes service availability from resource use. Local storage repair has its own Admin section. Product copy stays concise; maintenance guides describe extension rules for future tabs.
- Verification: all 50 browser E2E checks passed; frontend build, resource embedding and the separate Windows PyInstaller candidate completed. Relocated executable checks passed, including embedded dark/phone viewers, real log root, archive checksum and reader cleanup. Browser/relocated-package results, checksums, screenshots and traces are retained under `recovery/viewer-verification`; candidate is `dist/ui-redesign-20260926/RobotControl`. Native browser zoom could not be completed because computer-use app access timed out; real phone keyboard and VM hardware checks remain in the delivery checklist.

## 2026-09-26 Whole-application UI review

- Reviewed all active frontend routes, shared navigation/theme and the supplied log screenshot with two frontend specialists. Proposed four reusable page patterns, a shared space/action/state policy, System/Light/Dark appearance and route-by-route changes in `docs/frontend-ui-review-2026-09-26.md`.
- Identified missing first/last-page controls, excess log toolbars, tiny labware targets and code-reviewed state/save/pagination/polling problems to cover before the next redesign. This pass changed documentation only; no new application build or live-device verification was performed.

## 2026-09-26 Desktop and phone inspection viewers

- Two frontend specialists researched and peer-reviewed the shared inspection layout, table/full-row reader, searchable SQL catalogue and camera viewport. Back/Expand retain state; camera Fit preserves the whole frame, with explicit cropped Fill, zoom and bounded pan using the existing streaming session.
- RobotControl log browsing now uses the running logger's actual directory and permits remote administrators or authenticated local users. Complete plain/gzip/ZIP text is available through cancellable captured readers, bounded sections, section Find and opt-in live following. Source archives and existing retention behavior are preserved.
- Reader ownership, actual-peer access checks, Unicode/CRLF boundaries, temporary storage limits, idle expiry and startup/shutdown cleanup are enforced. Maintenance guides and repeatable browser/HTTP fixtures are updated; no new unit tests were added.
- Validation: all 29 browser/HTTP E2E checks passed, including deterministic camera focus recovery during a source-change gap. Frontend build, resource embedding and Windows compilation passed. The relocated candidate passed authenticated archive reconstruction, actual log-root, orphan cleanup and desktop/phone browser checks with disposable data and automation disabled. Physical camera/SQL and native phone-keyboard/browser-zoom acceptance remain VM/operator checks.
- Verification commands and limits: `frontend/e2e/README.md`. Retained reports, screenshots, traces and checksums: `recovery/viewer-verification/`. Windows candidate: `dist/viewer-review-20260926/RobotControl/` (copy the whole folder for VM testing).

## 2026-09-26 Remote timeout investigation

- Read-only probes reproduced intermittent pre-HTTP connection failure: 7/12 TCP timeouts, then five HTTP 200 responses; successful responses began about 0.30 seconds after connection. The development VM routes through its gateway, and ZeroTier peer state remained unavailable; the specific tunnel cause is unconfirmed.
- Actual-browser/HTTP reproduction confirmed that a held System Status response blocks serial polling and disables Refresh without showing a connection error. An explicit HTTP failure recovered after 30 seconds. Reviewed the separate five-second camera-delivery cutoff; no production code/settings changed.
- Repeatable harnesses and evidence remain Git-ignored under `recovery/20260926-remote-investigation/`. See `docs/remote-connection-review-2026-09-26.md` for findings, limitations and paired remote/local diagnostic steps. No executable rebuild was needed for this documentation-only review.

## 2026-09-17 Deployment recovery guidance and GitHub validation

- Documented full executable/support-folder replacement and reviewed offline reconciliation of conflicting live/archive run history, preserving originals and explicit scheduler resume.
- Excluded local `recovery/` databases and reports from Git. Deployment data and generated binaries remain local.
- Validation: 316 backend tests passed with temporary data paths; all 80 frontend tests and the production frontend build passed. Frontend embedding and Windows PyInstaller compilation passed into `dist/github-validation-20260917/RobotControl`; the new executable was not launched against robot hardware.

## 2026-09-14 SQLite safety and explicit scheduler resume

- Recovery now commits schedule/global flags, revision and audit together. Database guards reject recovery/running-run deletion and archive; queued deletion preserves cancelled history. Ordinary edits no longer overwrite recovery fields.
- Added missing-schedule acknowledgement and a separate persisted Resume action. Local operators must confirm robot readiness; stale revisions and unknown HxRun state block changes. Storage failures pause dispatch and retain monitoring.
- Enabled SQLite foreign keys, replaced execution REPLACE writes with upsert, preserved orphan notification metadata, and added reviewed administrator health/repair with verified retained backups for scheduling/authentication databases.
- Validation: 191 backend tests and 80 frontend tests passed. Frontend embedding and Windows PyInstaller compilation passed. The final executable passed isolated clean/legacy SQLite smoke checks, reviewed repair, missing-schedule acknowledgement, restart persistence and explicit Resume, with automation disabled and no robot methods launched.
- Built into `dist/sqlite-safety-release/RobotControl` using the new optional `--output-dir`, preserving the existing executable folder and its runtime databases.
- See `docs/maintenance/backend/sqlite-safety-maintenance-guide.md` for APIs, locking, reviewed repairs and offline restore. Tests use isolated databases and mocked robot execution.

# RobotControl Development Log (Chronological)

## 2026-09-14 Camera controls, stale-frame display and packaged validation

- Live streaming now includes admin camera discovery/selection, connect/reconnect and recording controls. Capture, recording and viewer connection are separate. Selection/focus survives polling; operation errors stay inline and requests abort on navigation. Reconnect live view affects only that viewer.
- The shared frame store timestamps receipt even for identical images. Inline/fullscreen overlays mark missing frames stale after ten seconds without rerendering the page per frame. No motion/frozen-image detector is introduced.
- Hardware validation found and fixed a DirectShow COM apartment conflict. First selection after camera-less startup retains recording intent. A spawned blocked-worker regression test verifies termination/reaping. Full backend suite: 283 passing; frontend suite and final focused camera tests pass.
- Isolated Windows package recording, WebSocket delivery, manual reconnect, preview-only reconnect after stop, readable clips and helper cleanup passed using a redirected Logi C270. See `docs/camera-recovery-validation.md`. Direct USB unplug/replug, actual multi-device/remote workloads and endurance remain unverified. Previous packages/runtime data are preserved.

## 2026-09-14 Camera health and manual control APIs

Added authenticated cached camera health and admin-only asynchronous discovery, selection, connect/reconnect and recording operations. Existing numeric recording routes execute off the event loop. Automatic startup retains recording intent when no camera is available and the later manual connection reattaches archival monitoring without duplicate callbacks. Health distinguishes frame freshness from recording and reports generations/progress to opt-in diagnostics. Partial clips are excluded from storage cleanup and download. Full backend suite: 281 passing.

## 2026-09-14 Camera process ownership and device identity

Camera capture and MJPEG writing now run in one spawned helper. The parent owns serialized operations, fixed-size preview IPC, generation checks and clip acknowledgements. Manual reconnect verifies helper exit before replacement. DirectShow metadata enumeration replaces capture probing; selection is saved by device identity. Finalized clips carry actual metadata sidecars; interrupted clips remain partial. Packaged children divert before application startup. Lifecycle and worker tests use isolated storage and mocked devices (22 passing).

## 2026-09-14 Bounded camera delivery and N100 candidate

- Streaming wakes on coalesced frame notifications, shares current-frame JPEG variants in two bounded encoding workers, and gives each viewer one latest-frame slot and an independent delivery task. Slow/disconnected viewers cannot backlog native work or block other viewers. Existing recording/quality settings and resource guard remain intact.
- Camera images use a shared current-frame store for inline/fullscreen rendering; the containing page no longer rerenders per frame. Pending session creation is aborted on unmount, socket handlers are detached on cleanup, and per-frame console logging is removed. Video attachment preparation now releases captures and partial outputs on failure. Diagnostics also sample event-loop task counts.
- Final automated validation: 278 backend tests and 69 frontend tests pass; production frontend build, embedding and isolated Windows PyInstaller packaging pass. Package smoke test verified all 22 JavaScript assets, authenticated sampled health, and two diagnostic samples. Candidate: `dist/RobotControl-optimized/RobotControl.exe` with `_internal`; runtime data and previous packages are preserved.
- Browser checks used an isolated synthetic fixture: a schedule draft/dropdown survived multiple polling cycles; 1,000 methods remained paged at 25; inline/fullscreen video and a separate status view remained usable, including narrow layouts and background streaming. These are not real remote-network/camera endurance results.
- Three ten-second probe trials per scenario against `d228f51` reduce repeated buffer reads about 61–67% with comparable delivered frames. Two-viewer CPU improves, but one-viewer CPU increases slightly with worker overhead; see `docs/performance-report.md` and raw measurements. N100 real-camera, 24-hour and ten-day acceptance remain pending; no long-term memory-leak resolution is claimed.

---

## 2026-09-14 Serialized UI polling and non-blocking status reads

- System Status uses one request/retry owner: 60-second normal refresh, existing 30-second recovery cadence, no overlaps or callback-driven restart loop, and stale/auth-changed response protection. Hidden pages retain polling. History no longer instantiates the entire scheduler hook and its duplicate background requests; it has its own serial history loader. Simultaneous queue/status reads are coalesced only while pending, scoped by login token.
- Added a shared five-second system-health sampler; REST and monitoring consume its timestamped snapshot instead of blocking for a one-second CPU sample. Blocking SQL calls in Database, Experiments and monitoring readers use the bounded Starlette thread pool. Operational dispatch/run monitoring freshness is unchanged.
- Added polling, cleanup, read-coalescing, sampler and event-loop responsiveness tests. Public API envelopes and database storage remain compatible.

---

## 2026-09-14 Streaming and attachment resource ownership

- Pending camera sessions now expire using the existing 60-second timeout; duplicate WebSocket attachments cannot replace live handlers. Failure/disconnect cleanup checks handler identity, detaches under lock and closes sockets outside the lock with an idempotent bounded close.
- Camera filesystem cleanup permits only one queued/running job. Alert attachment cleanup now covers preparation failures as well as SMTP failures.
- Added accelerated 100-session abandonment and duplicate/failed attachment tests. These fixes address demonstrated lifecycle defects; they do not establish the cause of the reported total-machine RAM growth.

---

## 2026-09-14 Resource baseline for N100 optimization

- Added opt-in 60-second JSONL diagnostics with bounded rotation, process-tree/private versus resident memory, SQL/browser separation, CPU/I/O and existing-service counts. Disabled by default; no allocation tracing, SQL tuning or operational service initialization.
- Added an isolated deterministic 720p streaming probe (zero/one/two viewers, three trials). Baseline from `d228f51` is in `docs/performance-baseline.json`; this is synthetic, not N100/camera/endurance evidence.
- Validation: 267 backend tests pass. See the performance maintenance guide for matched workload measurements and the required 24-hour/ten-day operator tests.

---

## 2026-09-14 Paged Logs workspace and Windows delivery

- Added per-source sidebar navigation, 50-entry paging (25/100 options), filename search across each directory/ZIP before pagination, metadata filters and deterministic sorting. Existing API callers retain the 200-entry default. Root/extension/local-session restrictions remain enforced, including direct archive requests.
- Replaced the bulky browser with a file panel and text reader: separate file/preview refresh, Latest/Beginning, preview-only Find, wrap, details/copy path, full-screen expansion and a narrow-screen Back/Reading tools flow. Successful folder/preview snapshots survive errors with stale explanations; superseded requests cannot replace newer content. Follow latest is opt-in, plain-file-only, waits for each request, stops when hidden/on error, and respects reading position.
- Browser validation covered 390/1280/1920 widths, source selection and Find retention, Escape/focus restoration, all new sidebar sections, a Cytomat draft retained across sections then discarded, and no streaming session started by Camera navigation. The packaged UI reached entries 201–250 of 1,816 logs. Tested 640×360 as the layout equivalent of 200% at 1280×720; native browser zoom remains an operator check.
- Validation: 65 focused frontend tests and 266 backend tests pass. Windows frontend build, resource embedding and isolated PyInstaller packaging succeed. SQL search and paged log reads were checked through the package. Candidate: `dist/RobotControl-browsing/RobotControl.exe` with `_internal`. Runtime data and earlier packages are preserved; disposable validation files and package-generated test data are removed after checks.

---

## 2026-09-14 Database browsing and applied queries

- Replaced the cramped table catalogue with a collapsible searchable panel and an explicit narrow-screen list/detail view. Removed fabricated 1,000-row counts. Tables retain rows during refresh, distinguish NULL/empty values, expose keyboard cell details and visible-column controls. Procedure/function browsing now has search and preserves its selection on refresh.
- Search and filter drafts apply explicitly. One cancellable request lifecycle protects table state from stale responses. Server search uses parameterized literal matches over supported scalar types; count and rows share predicates. Validated sort direction reaches both modern and legacy SQL pagination, with primary-key tie breaks and 30-second SQL command timeouts.
- Current-page/all-matching CSV and JSON exports use batches of at most 1,000 rows, progress/cancellation and a 50 MB guard. Changed counts and prematurely exhausted results fail explicitly; the UI explains that concurrent writes prevent snapshot guarantees.
- Validation: 15 SQL service tests and four focused component/export tests pass; TypeScript passes. Browser confirmed a real unmatched query returns zero rows, section Back retains the search draft, and 390px uses a Back-to-tables view without page overflow. No SQL records were changed.

---

## 2026-09-14 Section navigation across operational functions

- Shared permission-aware section registry now drives Database, Camera, Labware, Logs, Administration and Scheduling sidebar links, rail menus, breadcrumbs and URL selection. Base routes and Scheduling numeric navigation remain compatible; invalid/inaccessible section links fall back safely.
- Removed duplicate page tabs/source selection. Visited Database/Camera/Labware panels retain their local state; hidden Labware panels stop polling, preserving pending edits. Section navigation does not start/stop camera sessions or execute database operations.
- Navigation tests cover new rail menus and the distinct admin-or-local Restore/local-only Operations and RobotControl log rules. TypeScript checks pass. Browser integration and Windows packaging follow with the browsing changes.

---

## 2026-09-14 Compact application pages and layout validation

- Added shared page content/headers, one compact account/breadcrumb bar, fluid operational widths and bounded settings/readable content. Scheduling now has heading actions and a service strip; list/runtime columns follow actual available width. At 1280×720, normal operational content begins around 190px. Removed duplicate page navigation rows and the duplicate system-monitoring title.
- Browser integration polished folder breadcrumbs, common-root relative paths, method-table scrolling and sidebar expansion labels. Create/cleanup pickers preserve drafts and restore focus; a dropdown remained open with its draft and scroll through two polling cycles. Reviewed narrow and desktop layouts with 1,000 disposable imported methods. In-app browser zoom shortcuts are unavailable; checked the equivalent 640×360 layout for 200% zoom, with native zoom still requiring an operator check.
- Validation: 50 focused frontend tests and the full 260-test backend suite pass. Windows frontend build, resource embedding and isolated PyInstaller packaging pass. Packaged UI checks covered the 1,000-method library, page-only selection across two pages, search clearing selection, refresh retention and opening the saved method folder. Embedded JavaScript matches the final build.
- Candidate: `dist/RobotControl-layout/RobotControl.exe` with `_internal`. Removed disposable package data and validation fixtures; preserved the running installation and earlier candidates. No API, SQLite, scheduling/execution or live runtime-data changes.

---

## 2026-09-14 Shared sidebar and Scheduling section links

- Replaced desktop tabs/mobile-only navigation with one responsive AppSidebar and shared permission-aware navigation definitions. Desktop uses a remembered 240px/64px preference (expanded initially at 1440px); below 900px it becomes an overlay. Scheduling exposes its seven sections inline or in a collapsed-rail menu, with the latest observed recovery warning.
- Scheduling sections now use stable `?section=` links, including creation/recovery/notification handoffs; invalid or inaccessible sections return to Schedules. Added role/local-access, URL history, mobile-close, preference and keyboard tests. Global shortcuts defer to open MUI modals/menus so drafts and focus restoration remain intact.

---

## 2026-09-14 Folder-first method selection

- Added a shared catalogue-only folder explorer for primary/cleanup selection and Methods management. It compresses empty ancestor chains, supports drive/UNC roots and global name/path search, and keeps relative legacy paths in Needs path review. Picker confirmation is explicit; cancel and catalogue refresh preserve the schedule draft.
- Added 25/50/100-row pagination, page-scoped bulk selection that persists across pages, concise relative paths and full-path copying. Folder/search/filter changes clear management selection; refresh retains browsing state. Added 1,000-method, keyboard, cancellation, pagination and refresh regressions. No backend API or database changes.

---

## 2026-09-12 Reviewed method path correction

- Added manual/host-browser path correction with validated preview, separate primary/cleanup references, unchecked selection and disabled busy/archived schedules. Save revalidates the file, catalogue revision and selected schedule versions; catalogue and selected paths commit in one SQLite transaction. Scheduler locks coordinate enqueue/dispatch and cache refresh. Ordinary edit/archive writes cannot overwrite a concurrent correction; version checks no longer accept changes within a one-second tolerance.
- Unselected paths, labels, timing, contacts, archive state, import provenance, execution history and monitoring records stay intact. Canonical path collisions and stale previews fail without partial changes. Conflict messages preserve the draft and require a fresh review.
- Validation: 260 backend tests and 31 focused frontend tests pass, including rollback, enqueue/edit/archive races and paused monitoring preservation. Browser checks confirmed direct host-folder preview, archive/restore, cleanup-only correction, keyboard focus restoration and desktop/narrow layouts. Frontend build, resource embedding and Windows PyInstaller packaging pass. The isolated packaged app passed host browsing/import, archived reimport/restore, cleanup-only correction, stale-edit rejection, path checks and local-only access with its scheduler stopped.
- Candidate: `dist/RobotControl-method-library/RobotControl.exe` with its `_internal` directory. Validation data was removed; existing `dist/RobotControl`, `dist/RobotControl-setup` and runtime data were preserved. No Hamilton method was executed or email sent during validation.

---

## 2026-09-12 Method library management

- Added a local Methods tab with search, folder/status/archive filters, sorting, path checks, usage details (including cleanup references), schedule creation and selected archive/restore actions. Existing schedule paths and files are unchanged by archive; saved form selections remain visible when absent from new choices.
- Added backward-compatible archive, revision and validation fields. Checks persist Available/Missing/Inaccessible/Invalid/Not checked separately from archive. Revision checks reject stale changes. Reimport preserves archive and provenance and prefers a unique current entry over archived duplicates. Migration and API tests cover legacy validity, access, reimport, references and unchanged schedules.

---

## 2026-09-12 Host folder browsing for method import

- Replaced browser uploads with a local host folder browser: breadcrumbs, drives, parent navigation, imported-folder shortcuts and automatic absolute-path selection. Manual entry remains available and explains the missing required path. Failed navigation preserves the last usable folder/selection; linked folders are disabled.
- Added local-only `/experiments/browse` metadata access and shared directory helpers with the existing system browser, preserving database-restore behavior. Import still uses the existing host validation and per-file outcomes. Targeted backend and frontend tests cover navigation, access failures, linked folders and direct preview handoff.

---

## 2026-09-12 Verified Hamilton method import

- Replaced the import dialog with Choose folder → Review methods → Import results. Both browser and manual modes require an absolute host folder; selection sends paths only. Valid New/Update rows are selected by default, invalid rows explain failures, and searchable results report actual Added/Updated/Failed outcomes. Creating a schedule remains an explicit next action.
- Added a local-only, read-only preview endpoint and shared host filesystem validation for both import routes. Imports revalidate containment, metadata and case-insensitive `.med` files, preserve valid absolute-path callers, and reject unresolved relative requests. Canonical paths identify methods; old records are never automatically repaired or deleted. Database outcomes account for per-file failures and transaction rollback.
- Validation: all 235 backend tests and 25 focused frontend tests pass; TypeScript/Vite build, resource embedding and Windows PyInstaller packaging pass. Canonical-path regressions cover older path spellings without replacing record IDs and ambiguous legacy duplicates without automatic repair. Browser checks covered draft/focus/scroll stability across polling, keyboard/dropdown behavior, import preview/results/schedule handoff, and SMTP/import at 390px and 1280px widths. The isolated packaged app passed embedded UI/authentication, preview, Added/Updated results and local-access checks using disposable metadata files, never executable Hamilton methods.
- Candidate build: `dist/RobotControl-setup/RobotControl.exe` with its `_internal` directory. Existing `dist/RobotControl` and runtime data were preserved; the candidate contains no validation data. Operator simulator checks remain: pause/resume alerts, restart during an already-alerted pause without duplicates, and silence after completion. No real email was sent or Hamilton run launched during validation.

---

## 2026-09-12 Clear SMTP account setup

- Reorganized email setup around one account address, with existing custom login/From addresses preserved under Advanced settings. A single security selector replaces mutually exclusive switches and never silently changes ports. Manual recovery correctly falls back to the schedule's active contacts.
- A shared draft serializer preserves existing API/password semantics. Blank keeps the encrypted password; explicit replacement/removal is sent only on Save, with undo before saving. Refresh/discard requires an explicit choice for dirty drafts and retains entries after failures.
- Save precedes Test; dirty settings cannot be tested, saves never send email, and test progress/results stay inline. Twenty-one focused frontend tests and TypeScript checks passed. Browser review used an isolated instance; no real credentials were changed and no external email was sent.

---

## 2026-09-12 Stable schedule form refresh

- Removed duplicate custom focus trapping from create/edit and method import dialogs; MUI manages focus restoration and trapping. Schedule initial focus runs once on entry, and drafts initialize only once per open session. Polling and refreshed props cannot overwrite entered values or expanded sections.
- Edit saves use the version captured on opening, preserve drafts after conflicts, and explain how to reload. Removed duplicate post-save list fetches. Empty recipient selection now has an explicit warning that observation continues without email delivery.
- Nine frontend tests passed, including two simulated 30-second refreshes preserving focus/scroll/data, reopening a fresh draft, and retaining entries after a save conflict. TypeScript checks passed. Browser/package acceptance continues on an isolated instance.

---

## 2026-09-12 Hamilton paused-state consistency

- Confirmed mapping: 1 = Running, 2 = Paused. Shared SQL mapping, experiment enum, dashboard/system display, monitoring API progress and scheduler/email diagnostics now agree. Paused remains an unfinished execution and never invokes recording completion.
- The exact trace is observed in both states. SQL state transitions do not reset inactivity or create a new pause; trace writes do. Observation/status/email context includes the normalized and raw SQL state, with backward-compatible defaults for saved observations.
- Added regression coverage for state parsing, pause/resume/restart deduplication, terminal priority, progress and completion callbacks, plus a minimal frontend test harness for this and subsequent UI changes. Operator simulator acceptance remains required after packaging.
- Validation: 79 targeted backend tests, six frontend status tests, and the Windows frontend build passed. The Vitest harness leaves the existing legacy Jest suites unchanged and excludes them pending a separate migration.

---

## 2026-09-12 Simulator acceptance checkpoint

- Operator testing confirmed real SMTP delivery and one `log_inactive` email. Notification history records that email at 13:04:51, followed by `monitoring_unavailable` emails at 13:09:21 and 13:17:37. Receiving three messages does not yet verify repeated inactivity alerts.
- Restart at approximately 13:10 restored the same execution and Hamilton GUID without creating another execution. The unavailable warning also occurred before restart, so it is not specific to restoration.
- Read-only SQL inspection while the simulator was paused returned `RunState = 2`, with no end time; the matching trace recorded a pause. The current mapping recognizes numeric states 1, 64 and 128 only. State 2 therefore becomes unknown and triggers the unavailable warning instead of continuing trace observation. This is a known limitation of this checkpoint; the next change should handle the observed pause state explicitly, retain terminal-state priority, and report unknown raw states clearly.
- SMTP delivery now works with the operator's corrected QQ settings. Schedule contacts must be selected separately from creating a global contact; missing recipients appear as delivery errors. Clearer sender/login labels and recipient warnings remain follow-up work.
- Existing validation remains 205 passing backend tests, successful frontend/resource/Windows builds, and isolated packaged responsiveness checks. Full simulator pause/rearm acceptance, restart during an already-alerted pause, and completion silence remain to be verified after the pause-state correction. This checkpoint changes documentation only after those builds; it does not alter the running application.

---

## 2026-09-12 Email responsiveness and Hamilton process inspection

- Fixed API freezes during test/custom email sending and manual recovery actions by moving blocking work to the request thread pool. Interactive email uses one attempt with a 10-second timeout per SMTP operation; the test-email UI waits up to 60 seconds for the detailed result. Background monitoring delivery retains its retry policy.
- SMTP failures now identify the host, port and failed step (connection/greeting, TLS, authentication or submission). TLS verifies server certificates, rejected credentials are not repeatedly retried, and socket cleanup cannot cause an accepted email to be resent.
- Replaced the scheduler process monitor's shared WMI/COM client with the existing psutil dependency. Busy checks and status details share one detection path; a hidden, five-second tasklist fallback handles unavailable inspection. Unusable detection reports an error and blocks dispatch. Background monitoring stops promptly and can restart.
- All 205 backend tests and the frontend build passed. Tests cover responsive concurrent API requests during stalled email/recovery, SMTP failures/retries and process inspection/recovery from background threads. Native Windows main/worker/background process checks passed. Independent unauthenticated Gmail probes timed out at the greeting on port 587 and TLS handshake on port 465; actual external email delivery remains dependent on resolving SMTP connectivity. Camera behavior was left unchanged as requested.
- Resource embedding and the standard Windows PyInstaller build passed. The isolated executable sent to a loopback SMTP stub, then returned a deliberate greeting timeout after 10.23 seconds while 14 concurrent health/queue checks remained responsive. Background process monitoring and scheduler restart passed without COM errors. Original runtime data was restored with hash verification, temporary test/build copies were removed, and the user app remains stopped. No external email or Hamilton method was launched during validation.

---

## 2026-09-12 Scheduler run log inactivity monitoring

- Replaced the twice-estimated-duration watchdog with exact SQL RunGUID-to-trace monitoring. Each schedule has a positive whole-minute threshold (default 3); changes apply to the next launch. Actual cleanup targets are tracked. Removed the executor's 120-minute process kill while retaining late-start cleanup behavior.
- Added durable observation state and per-pause email identifiers. SQL/file outages get a distinct three-minute warning; new trace activity rearms inactivity alerts. Email retries/attachments run on one background delivery worker, with exact trace selection and revalidation before sending.
- Startup restores observations and preserves alert deduplication. Shared atomic finalization reconciles process/SQL outcomes once, including archived executions. Existing manual recovery acknowledgement can close unowned orphan observations only after HxRun is absent.
- Added API/model/storage/form wiring, running-job monitoring details, and maintenance guidance. All 181 backend tests passed, covering threshold validation, trace matching, outages, restart, retries, terminal races, archival and unlimited runtime.
- Frontend build, resource embedding and Windows PyInstaller packaging passed. The isolated executable passed health, OpenAPI, embedded scheduling UI, authenticated queue and disabled-schedule create/update checks (default 3; omitted updates preserve the setting). Read-only live SQL lookup matched an exact local trace. Existing packaged runtime data was restored with file-hash verification; temporary smoke files were removed. Operator-led Hamilton simulator pause/resume/restart and real email delivery remain to be checked.

---

## 2026-09-12 uv migration and Windows setup

- Replaced both conflicting requirements files with one root uv project and lockfile; pinned managed Python 3.14.7, modernized application dependencies, and separated dev/build groups. Passlib 1.7.4 and bcrypt 4.3.0 remain pinned to preserve existing password hashes. Windows dependencies include pywin32 and WMI.
- Installed user-local uv and Node.js 24/npm, synchronized `.venv`, and built the frontend. Updated setup, maintenance, and packaging instructions and aligned the existing backend Docker recipe and nginx proxy with port 8005.
- Repaired stale test imports, property mocks, SQLite singleton isolation, Windows file-lock simulation, and scheduler polling timing. Replaced obsolete failover database tests with primary-only service tests and added stored-password compatibility coverage.
- Enabled the recording download handler's existing HEAD behavior with separate OpenAPI operation IDs. Moved process-wide shutdown hooks into the entrypoint so test and packaging imports do not register them. Added optional `ROBOTCONTROL_AUTO_RECORDING_ENABLED=0` for interface development; automatic recording remains enabled by default.
- Fixed Hamilton busy detection when a worker cannot use WMI's COM connection: fall back to `tasklist`, and block dispatch if process detection fails. Regression tests cover COM failures, busy/idle results, timeouts, and command errors.
- PyInstaller now collects application modules and embedded frontend assets without copying backend tests, local configuration, or runtime data. A fresh `uv sync --locked`, lockfile check, dependency compatibility check, all **141 backend tests**, frontend build, and final Windows onedir build passed. Existing dependency/deprecation warnings remain.
- Verified source and compiled `/health`, `/openapi.json`, frontend/JavaScript assets, browser login, authenticated profile requests, and refresh-token persistence across restart. Verified graceful shutdown in source and a temporary compiled console build; the tray's Terminate menu was not automated. The independent reviewer completed a follow-up review after both findings were fixed and reported no remaining actionable issues.
- Live robot actions and camera recording were not exercised. A read-only SQL dashboard query succeeded on this host; full SQL workflows, Linux deployment, and a separate VM remain unverified. The standard executable is retained at `dist/RobotControl/RobotControl.exe`; temporary downloads, test files, and the console smoke build were removed.

---
## 2026-02-24 LogFile Remote Access Split (Per Source)

- Removed the frontend’s page-wide local-session block for LogFile and switched to source-level availability messaging/selection state, so remote `user/admin` sessions can use allowed sources (`frontend/src/pages/LogFilePage.tsx`).
- Added backend per-source access policy (`access_scope`) in `backend/api/logfiles.py`: `Python Log` and `Hamilton LogFiles` are remote-accessible, while `RobotControl Logs` remains local-only.
- `GET /api/logfiles/sources` now returns per-source `permissions.can_access` and `access_scope`, and browse/preview endpoints enforce access after source resolution.

---
## 2026-02-24 LogFile Hamilton Source Filter (TRC Only)

- Restricted the `Hamilton LogFiles` LogFile source to `.trc` files only (directories still visible for navigation), so non-log files in that folder no longer appear in the LogFile page and direct preview requests for non-`.trc` files are rejected (`backend/api/logfiles.py`).
- Added backend tests covering Hamilton source filtering and non-`.trc` preview rejection (`backend/tests/test_logfiles_api.py`).

---
## 2026-02-24 LogFile Review (Dedicated Tab + Archive-Aware Viewer)

- Added a new top-level **LogFile** page/route (`/logfile`) for read-only log browsing and previewing, with desktop tab/mobile drawer/breadcrumb/keyboard shortcut integration (`frontend/src/App.tsx`, `frontend/src/pages/LogFilePage.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added a dedicated backend API router `backend/api/logfiles.py` (`/api/logfiles/*`) using a fixed allowlist of log roots (Python Log, Hamilton LogFiles, RobotControl logs) instead of arbitrary path browsing.
- Implemented preview support for normal text logs plus `.gz` history logs and `.zip` archive browsing/preview, with `head`/`tail` modes and server-side preview size caps.
- Added graceful handling for locked/in-use files by returning a structured `423 FILE_LOCKED` response so the UI can show a warning instead of failing the whole page.
- Added backend tests covering source listing, traversal rejection, text preview, gzip preview, zip archive browsing/preview, and locked-file error handling (`backend/tests/test_logfiles_api.py`).
- Added LogFile maintenance guides for backend/frontend and updated main application maintenance guides to include the new router/page (`docs/maintenance/backend/logfile-maintenance-guide.md`, `docs/maintenance/frontend/logfile-frontend-maintenance-guide.md`, `docs/maintenance/backend/main-application-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).

---
## 2026-02-22 OD Auto-Reschedule Email Notification (Schedule Contacts)

- Added `POST /api/scheduling/notifications/send` to send a custom email through the existing SMTP settings to the active notification contacts attached to a specific schedule (`backend/api/scheduling.py`).
- Updated `backend/scripts/scheduling_api_cli.py` (OD prediction auto-rescheduler) to send a schedule-contact email only after a successful schedule update, including previous vs updated start time plus OD summary context (last data timestamp and average latest OD per culture).
- Email delivery failures are logged as warnings in the CLI and do not roll back the successful reschedule.
- Updated backend scheduling maintenance guide with the new endpoint/CLI behavior (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduling API CLI Prerequisites Visibility

- Updated `backend/scripts/scheduling_api_cli.py` list/update row rendering to include `prerequisites`, so external operators can identify required pre-execution database flags while selecting target schedules.
- Updated scheduling backend maintenance guide to document that `list` now shows `prerequisites` (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduling API Automation CLI (Target + Update Without Frontend)

- Added `backend/scripts/scheduling_api_cli.py`, a small script for backend-only scheduling automation:
  - `list` command to find target schedules by ID/name.
  - `update` command to patch one schedule directly through `PUT /api/scheduling/{schedule_id}`.
- Script performs login (`/api/auth/login`), handles bearer auth, supports optional `X-Forwarded-For`, and uses `expected_updated_at` optimistic locking by default by fetching a fresh schedule snapshot before updating.
- Updated backend scheduling maintenance guide with a new section documenting external API automation workflow and concrete command examples (`docs/maintenance/backend/scheduling-maintenance-guide.md`).

---
## 2026-02-18 Scheduler Blueprint Reconciliation (SCHEDULER_FULL_PICTURE)

- Revalidated `SCHEDULER_FULL_PICTURE.txt` against current scheduling code (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`, `backend/api/scheduling.py`) and rewrote stale sections so the file can be used as handbook blueprint.
- Removed outdated retry/`RetryConfig` descriptions and replaced them with current `TimeoutConfig` behavior (`continue` vs `run_cleanup_and_terminate`) including queue-wait-aware timeout evaluation at launch time.
- Documented real single-worker dispatch gating (`HxRun maintenance`, `manual recovery`, `schedule recovery_required`, `HxRun busy`), queue `waiting_reason`, and cancellation behavior for removed/deactivated schedules before dispatch.
- Clarified current API constraints in plain language: no duplicate-minute guard, preserved timestamp precision, create-time past-start rejection, and runtime-truth queue status from `/api/scheduling/status/queue`.

---
## 2026-02-18 Queue-First Dispatch Refactor (Checks Folded Into Worker)

- Refactored scheduler dispatch to queue-first behavior: due jobs are always queued, and HxRun maintenance/manual recovery/HxRun busy checks now run inside the single worker before switching a job from queued to running (`backend/services/scheduling/scheduler_engine.py`).
- Added runtime queue metadata (`queued_at`, `waiting_reason`) so blocked jobs remain visible as queued (not running) with explicit wait reasons in `/api/scheduling/status/queue`.
- Updated executor contract to focus on launch + timeout action resolution only; scheduler worker now owns readiness gating (maintenance/manual/busy checks) (`backend/services/scheduling/experiment_executor.py`).
- Updated schedule list next-run rendering to use backend canonical timestamp directly (removed client interval recomputation), preventing UI drift where displayed due time differs from actual launch timing (`frontend/src/types/scheduling.ts`, `frontend/src/components/ScheduleList.tsx`).
- Added regression coverage for “busy robot keeps schedule queued until available,” and refreshed executor timeout-action tests to match the new worker-owned gating model (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_hxrun_maintenance_executor.py`).

---
## 2026-02-18 Scheduler Timeout Refactor (No Retry Logic + Queue Visibility)

- Replaced schedule retry configuration with timeout configuration across backend models/API/storage: schedules now persist `timeout_config` (`timeout_minutes`, `action`, optional cleanup method) and no longer accept/use `retry_config` (`backend/models.py`, `backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`).
- Simplified execution path to single-attempt launches: removed executor retry loop, added timeout action routing (`continue` or `run_cleanup_and_terminate`), tied HxRun-availability wait to schedule timeout when configured, and when cleanup action is triggered the schedule is deactivated for subsequent runs (`backend/services/scheduling/experiment_executor.py`, `backend/services/scheduling/scheduler_engine.py`).
- Added create-time start timestamp guard in backend (`start_time` cannot be in the past) and updated scheduling create-guard tests, including new rejection coverage for past timestamps (`backend/api/scheduling.py`, `backend/tests/test_scheduling_create_guard.py`).
- Extended scheduler tests for timeout cleanup termination behavior and adjusted executor-maintenance test stubs for the new single-attempt executor contract (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_hxrun_maintenance_executor.py`).
- Updated frontend scheduling types/services/forms/pages for timeout config editing and rendering, removed retry fields from scheduling payloads, and added a runtime queue panel that shows both running and queued schedules from `queueStatus` (`frontend/src/types/scheduling.ts`, `frontend/src/services/schedulingApi.ts`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Updated scheduling maintenance guides to document timeout behavior and queue detail surfaces (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`).

## 2026-02-17 Scheduler Policy Simplification (No Lateness Miss, No Timestamp Guard)

- Removed lateness-based miss rules from due-job detection; scheduler now enqueues any active schedule whose `start_time <= now` and no longer auto-marks overdue jobs as `missed` based on fixed thresholds (`backend/services/scheduling/scheduler_engine.py`).
- Removed API timestamp constraints on schedule create/update: no minute rounding and no duplicate-minute conflict checks (`backend/api/scheduling.py`).
- Removed now-unused duplicate-minute lookup helpers from scheduling DB manager/SQLite layers (`backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Updated schedule create/update tests to match the new policy (timestamps are accepted as provided and duplicate-minute checks are not enforced) (`backend/tests/test_scheduling_create_guard.py`).
- Fixed double error pop-up on save failures by keeping create/update failures local to the form dialog path (throw to caller without setting page-level scheduling error banner in mutation handlers) (`frontend/src/hooks/useScheduling.ts`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Updated scheduler maintenance/explainer docs to reflect the simplified behavior (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`, `SCHEDULER_FULL_PICTURE.txt`).

## 2026-02-17 Scheduling Form Save-Failure Dialog (No Silent Close)

- Fixed scheduling create/update mutation behavior so failures now propagate to callers instead of being swallowed inside `useScheduling`; the hook still sets `state.error`, but now also throws to let dialog submit handlers react (`frontend/src/hooks/useScheduling.ts`).
- This enables `ImprovedScheduleForm` submit flow to keep the form open and show `StatusDialog` (for example on duplicate active timestamp `409`) instead of closing as if save succeeded (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Updated frontend scheduling maintenance docs to reflect this contract: read-path errors remain inline (`state.error`), while create/update form failures should be handled via `try/catch` + modal status dialog (`docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`).

## 2026-02-17 Single-Worker Scheduler Queue + Minute Timestamp Guard

- Reworked scheduler dispatch to a true single-worker queue model: due jobs are enqueued and consumed serially by `SchedulerJobWorker`, and the legacy scheduler-side capacity reservation/retry layer was removed to avoid double-gating before HxRun launch (`backend/services/scheduling/scheduler_engine.py`).
- Updated `/api/scheduling/status/queue` to report queue/running snapshots directly from scheduler runtime state instead of the detached legacy queue manager so UI queue status reflects actual execution flow (`backend/api/scheduling.py`, `backend/services/scheduling/scheduler_engine.py`).
- Added a minute guard for active schedule timestamps on both create and update: incoming `start_time` values are normalized to minute precision and conflicts are rejected when another active non-archived schedule already uses that minute (`backend/api/scheduling.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Normalized manual-recovery timestamp persistence to one local-naive serialization path for mark/resolve/global recovery writes, eliminating the previous UTC-vs-local inconsistency (`backend/services/scheduling/sqlite_database.py`).
- Added regression coverage for single-worker serial execution behavior plus duplicate-minute create/update rejection and timestamp normalization (`backend/tests/test_scheduler_single_worker.py`, `backend/tests/test_scheduling_create_guard.py`).
- Refreshed scheduler documentation to match the new architecture and rewrote the root-level plain-language explainer for the current flow (`docs/maintenance/backend/scheduling-maintenance-guide.md`, `SCHEDULER_FULL_PICTURE.txt`).

## 2026-02-14 Labware Cytomat Visualization + Controlled PlateID Editing

- Added a dedicated Cytomat backend service and API endpoints under `/api/labware/cytomat` so users can view `CytomatPos` + `PlateID` and apply batch `PlateID` updates with the same auth/locality guard model as TipTracking (`backend/services/labware_cytomat.py`, `backend/api/labware.py`).
- Cytomat dropdown options are now sourced from `Plates.PlateID`, with ordering enforced as: empty option first, then descending numeric IDs, then descending non-numeric IDs; empty selection is persisted as `NULL` in `Cytomat.PlateID`.
- Added a new Labware secondary tab and Cytomat UI panel with row-level dropdown editing, pending-change queue, save/discard controls, read-only behavior for remote sessions, and refresh/autorefresh behavior (`frontend/src/pages/LabwarePage.tsx`, `frontend/src/components/labware/CytomatPanel.tsx`, `frontend/src/services/labwareApi.ts`).
- Added backend API regression coverage for Cytomat read permissions, local-only write enforcement, successful local writes, and invalid PlateID rejection (`backend/tests/test_labware_api.py`).
- Updated backend/frontend labware maintenance guides to document the new Cytomat module and maintenance workflow (`docs/maintenance/backend/labware-maintenance-guide.md`, `docs/maintenance/frontend/labware-frontend-maintenance-guide.md`).

---
## 2026-02-14 HxRun Maintenance Enable Guard (Do Not Kill Existing Session)

- Added a backend pre-check on `PUT /api/maintenance/hxrun`: when enabling maintenance mode, RobotControl now first checks if `HxRun.exe` is already running and blocks the toggle with `409` instead of enabling and terminating HxRun (`backend/api/maintenance.py`, `backend/services/hxrun_maintenance.py`).
- Added a clear operator-facing conflict message (`HxRun is running. Please close the software before entering maintenance mode.`) so local users know exactly why the toggle is rejected.
- Added API regression coverage for the blocked-enable path and verified that state persistence is skipped when HxRun is running (`backend/tests/test_hxrun_maintenance_api.py`).
- Updated the Maintenance page to show a dedicated dialog when this conflict happens, instead of silently failing or relying only on inline error text (`frontend/src/pages/MaintenancePage.tsx`).

## 2026-02-12 HxRun Maintenance Mode (Event + Fallback Enforcement)

- Added a new persistent **HxRun Maintenance Mode** (separate from the existing database-restore maintenance window) with a dedicated backend API: authenticated users can inspect state, while toggles require loopback/local access (`backend/api/maintenance.py`, `backend/main.py`).
- Extended scheduler SQLite global state to store `hxrun_maintenance_enabled` plus reason/user/timestamp metadata, including auto-migration for existing databases (`backend/services/scheduling/sqlite_database.py`, `backend/services/scheduling/database_manager.py`, `backend/models.py`).
- Introduced a global enforcement service that uses **event-driven process-start watching** for `HxRun.exe` with **1s fallback polling**; when enabled, any detected HxRun process is terminated and a Windows popup explains the block (`backend/services/hxrun_maintenance.py`, `backend/main.py`).
- Added hard backend guards so scheduler dispatch pauses while maintenance mode is enabled and experiment execution exits early with a clear maintenance-blocked error instead of launching HxRun (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`).
- Added an independent top-level `MAINTENANCE` page/tab between Labware and System Status, with local-only edit controls and remote read-only inspection (`frontend/src/pages/MaintenancePage.tsx`, `frontend/src/services/hxrunMaintenanceApi.ts`, `frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added API + executor regression tests for local/remote permissions and maintenance launch blocking (`backend/tests/test_hxrun_maintenance_api.py`, `backend/tests/test_hxrun_maintenance_executor.py`).

## 2026-02-12 Camera Download Resume + Retry

- Upgraded camera recording downloads to support resumable transfers over unstable links by adding `HEAD` + `GET` range handling on `/api/camera/recording/{recording_id}`; responses now include `Accept-Ranges`, `Content-Range` (for `206`), `ETag`, and `Last-Modified`, and return `416` for invalid ranges (`backend/api/camera.py`).
- Kept compatibility with existing archive UI endpoints while hardening transfer semantics (full download still works, partial resume now works, and `If-Range` mismatch correctly falls back to full-body responses).
- Fixed archive download file resolution for experiment recordings stored in nested subfolders: backend lookup now scans `experiments/` recursively and selects the newest match when duplicate filenames exist, which resolves false `404` responses for files visible in the archive list (`backend/api/camera.py`).
- Added API-focused regression tests that validate full download, partial download, suffix range, invalid range, `If-Range` fallback, and metadata-only `HEAD` behavior (`backend/tests/test_camera_download_api.py`).
- Reworked frontend archive download flow to support resume-aware retries with exponential backoff, live byte progress, and user cancellation; one active download can continue from the last successful byte instead of restarting from zero on transient network failures. Client now stops auto-retrying non-retryable `4xx` responses (notably `404`) and shows a direct error instead (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/camera/VideoArchiveTab.tsx`).

## 2026-02-12 Labware TipTracking Web Module

- Added a dedicated Labware backend module with SQL-backed tip tracking for `1000ul` and `300ul` families, including snapshot read APIs plus batch update/reset operations (`backend/services/labware_tip_tracking.py`, `backend/api/labware.py`, `backend/main.py`).
- Enforced the requested permission model: authenticated admin/user sessions can inspect tip state, while write endpoints require local network access via `require_local_access` (remote sessions are read-only by design).
- Added a new `LABWARE` top-level page between Camera and System Status with a secondary tab architecture (`TipTracking` as the first module) and a full interactive tip editor (select/apply tip, apply column, apply rack, pending queue, save/discard/reset, legend, auto-refresh) (`frontend/src/pages/LabwarePage.tsx`, `frontend/src/components/labware/TipTrackingPanel.tsx`, `frontend/src/services/labwareApi.ts`).
- Updated navigation and discoverability for the new route across desktop tabs, mobile drawer, breadcrumbs, and keyboard shortcuts/help text (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`).
- Added backend and frontend maintenance guides for the new module and refreshed main-application guides to list the new route/router (`docs/maintenance/backend/labware-maintenance-guide.md`, `docs/maintenance/frontend/labware-frontend-maintenance-guide.md`, `docs/maintenance/backend/main-application-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).

## 2025-10-22 Local Scheduling Guardrails

- Reworked schedule management controls to respect the session’s `session_is_local`/`last_login_ip_type` flags so remote browsers stay in read-only mode while the local workstation still gets full CRUD (`frontend/src/pages/SchedulingPage.tsx`).
- Hid the manual recovery action buttons for remote users while keeping the status display intact; handlers now short-circuit when the session is not local to prevent accidental calls from devtools (`frontend/src/pages/SchedulingPage.tsx`).
- Replaced the Database Operations tab with an informational card for remote sessions so destructive experiment tooling never renders outside the lab (`frontend/src/pages/DatabasePage.tsx`).
- Fixed the “local session” check to rely on the live `session_is_local` flag (with hostname fallback only when the flag is missing) so remote logins that previously logged in locally no longer gain restore or scheduling controls (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/pages/SchedulingPage.tsx`).
- Archived schedule deletion buttons now respect the same guard, keeping remote users from removing runs while still letting them review history (`frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-21 Schedule Timestamp Localisation

- Stopped writing UTC-naive strings for new schedules by stamping `created_at` / `updated_at` with the local wall-clock and persisting those values explicitly in SQLite (`backend/models.py`, `backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`).
- Guarded the Database Restore tab so only admins or users coming from a “local” login see the restore UI; remote non-admins now see a friendly notice instead of stacked API error pop-ups (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseRestore.tsx`).
- `AuthContext` now preserves the session metadata (`session_is_local`, IP classification, client IP) FastAPI returns, so future guards can make local-vs-remote decisions without another round trip (`frontend/src/context/AuthContext.tsx`).

## 2025-10-20 Restore Reconnect Hardening

- Fixed the maintenance bypass flag so `/health` polls escape the interceptor by checking `headers.has('X-Allow-Maintenance')` before rejecting, which lets the UI drop maintenance mode as soon as the backend responds (`frontend/src/services/api.ts`).
- Reworked the backup restore flow to open its own pyodbc connection, then clear pooled handles and wait for a clean `SELECT 1` before reporting success; the helper covers both managed `.bak` restores and the direct path workflow (`backend/services/backup.py`).
- Added a `reset_pools()` hook on the async connection manager so disruptive operations can drop stale handles, and wired `DatabaseConnectionManager.reset_pools()` through for legacy callers (`backend/core/database_connection.py`).
- Simplified the database service to use only the primary connection profile and removed the unused secondary config entry to reflect current deployments (`backend/services/database.py`, `backend/config.py`).

## 2025-10-20 Archived Deletion & Logging Cleanup

- Added delete controls to the archived schedules table/cards and route them through the existing confirmation dialog so archived jobs can be purged without switching tabs (`frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/types/scheduling.ts`).
- Disabled daily alias files in backend logging so `data/logs/` now only holds the live `robotcontrol_backend.log` and `robotcontrol_backend_error.log`; rotated files are compressed directly into `data/logs/history` (`backend/utils/logging_setup.py`).
- Reworked the system tray stop callback to flag the running uvicorn server to exit instead of calling `sys.exit`, which eliminates the `SystemExit` traceback from pystray when shutting down from the tray menu (`backend/main.py`).

## 2025-10-20 Restore Error Messaging

- Prevented Database Restore failures from firing both the modal status dialog and the page-level banner by removing the extra `onError` call in the restore handler, so users now see a single validation message when a restore cannot start (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-19 Modal Notifications

- Replaced every inline error/success banner with the modal-based `ErrorAlert` suite so feedback now appears as dialogs instead of shifting layouts; the shared component renders Material UI dialogs with retry/close actions (`frontend/src/components/ErrorAlert.tsx`).
- Updated all consumers—camera, scheduling, backups, authentication dialogs, and system settings—to trigger the modal notifications and removed legacy snackbars/alerts (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/BackupManager.tsx`, `frontend/src/pages/BackupPage.tsx`, `frontend/src/components/ChangePasswordDialog.tsx`, `frontend/src/components/SystemConfigSettings.tsx`, `frontend/src/components/scheduling/FolderImportDialog.tsx`, `frontend/src/components/BackupActions.tsx`, `frontend/src/components/BackupListComponent.tsx`).
- Trimmed success messaging so one concise dialog appears per action and removed redundant inline alerts (e.g., backup creation/deletion, database restore, experiment deletion) for a single-source notification (`frontend/src/components/ErrorAlert.tsx`, `frontend/src/components/BackupManager.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/DatabaseOperations.tsx`, `frontend/src/pages/BackupPage.tsx`).
- Adjusted restore confirmation copy so the warnings live directly in the dialog instead of duplicated modals, and clarified outage expectations in a short bullet list (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-19 Camera Stream Aspect Ratio

- Let the live streaming card size itself to the incoming frame by capturing each `<img>`’s natural dimensions and applying an `aspectRatio`, replacing the old fixed 360 px viewport so portrait feeds fill the panel while placeholders keep a sensible minimum height; the fullscreen control now appears only after frames arrive (`frontend/src/pages/CameraPage.tsx`).
- Kept the reusable camera viewer ready for portrait feeds by syncing its aspect ratio to each frame’s natural size (`frontend/src/components/CameraViewer.tsx`).

## 2025-10-19 Frontend Maintenance Guides

- Added idiot-proof walkthroughs for the authentication, camera, database, scheduling, monitoring, and application shell UI so every frontend module now has a matching maintenance manual (`docs/maintenance/frontend/authentication-frontend-maintenance-guide.md`, `docs/maintenance/frontend/camera-frontend-maintenance-guide.md`, `docs/maintenance/frontend/database-frontend-maintenance-guide.md`, `docs/maintenance/frontend/scheduling-frontend-maintenance-guide.md`, `docs/maintenance/frontend/monitoring-frontend-maintenance-guide.md`, `docs/maintenance/frontend/main-application-frontend-maintenance-guide.md`).
- Each guide mirrors the backend documentation style—high-level architecture, lifecycle steps, key state, tasks, extension patterns, and troubleshooting—so future contributors have consistent references across the stack.

## 2025-10-19 Maintenance Guides Expansion

- Documented the authentication stack for future operators, covering the `AuthService`, SQLite schema, REST endpoints, and frontend token wiring so password resets, token refreshes, and config tweaks stay predictable (`docs/maintenance/authentication-maintenance-guide.md`).
- Captured the full monitoring/notifications pipeline—background loops, experiment polling, WebSocket channels, and scheduler email alerts—so the real-time dashboard and alerting remain stable during tweaks (`docs/maintenance/monitoring-maintenance-guide.md`).
- Wrote a main-application guide describing FastAPI startup/shutdown, static asset serving, logging directories, and packaging scripts to make backend deployments and PyInstaller builds idiot-proof (`docs/maintenance/main-application-maintenance-guide.md`).

## 2025-10-18 Scheduling Maintenance Trim

- Added a project-level `.gitignore` so transient build outputs (PyInstaller bundles, frontend builds, venvs, caches) stop polluting status checks while still leaving the generated files in place for runtime use (`.gitignore`).
- Removed the obsolete `database_manager_backup.py` module entirely; all scheduling paths now import the single primary database manager implementation (`backend/services/scheduling/database_manager.py`).
- Encapsulated scheduler capacity acquisition in a dedicated helper, leaving `_execute_job` easier to follow while preserving the existing retry semantics and logging (`backend/services/scheduling/scheduler_engine.py`).
- Moved execution-history deduplication into the SQLite layer so the API now returns a single authoritative record per execution; the React view simply renders the list without client-side merging (`backend/services/scheduling/sqlite_database.py`, `frontend/src/components/ExecutionHistory.tsx`).
- Centralised manual-recovery normalisation in the scheduling API client so hooks and services share one mapping definition (`frontend/src/services/schedulingApi.ts`, `frontend/src/hooks/useScheduling.ts`).
- Dropped stale backend service singletons by making `get_services()` fetch fresh dependencies each call, avoiding hidden global state while keeping endpoint signatures unchanged (`backend/api/scheduling.py`).
- Removed the unused refactored camera route and demo components after folding their improvements into the main camera page, trimming dead UI code (`frontend/src/pages/CameraPageRefactored.tsx`, `frontend/src/components/examples/*`, `frontend/src/components/camera/index.ts`, `frontend/src/components/camera/TabPanel.tsx`).
- Simplified the camera backend to use the standard config/data-path helpers and rely solely on the shared frame buffer/LiveStreaming service for streaming, eliminating the legacy per-camera frame cache and fallback imports (`backend/services/camera.py`, `backend/services/live_streaming.py`, `backend/tests/test_camera.py`).
- Broke the backup service into a `SqlCommandExecutor` and `BackupMetadataStore`, removing duplicated SQL/metadata handling logic and making the core service focused on orchestration (`backend/services/backup.py`).

---
## 2025-10-17 Archive Feature Finalization

- Removed every reference to the legacy `failed_execution_count` field so new databases no longer create or maintain the column while existing files stay compatible; scheduling models, API payloads, and SQLite operations now ignore the obsolete counter (`backend/models.py`, `backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`, `frontend/src/types/scheduling.ts`, `frontend/src/services/schedulingApi.ts`).
- Hardened archive toggling on the backend by reusing the standard update path, forcing scheduler cache invalidation, and keeping optimistic locking timestamps accurate so archived schedules reliably stay dormant (`backend/api/scheduling.py`).
- Completed the frontend archive experience with dedicated loading states, list labelling, and hook state for archived schedules, allowing the “Archive” tab and buttons to stay in sync after archive/unarchive actions (`frontend/src/hooks/useScheduling.ts`, `frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-17 Scheduler Concurrency Queueing

- Added a backlog tracker for schedules deferred because the concurrency limit is hit so we log “Max concurrent jobs reached” only once per waiting job and avoid losing it from the queue (`backend/services/scheduling/scheduler_engine.py`).
- Prevented one-time schedules from being auto-marked “missed” while they are waiting for capacity, letting them run as soon as the current job finishes instead of flipping to “Not scheduled” (`backend/services/scheduling/scheduler_engine.py`).
- Folded the scheduler’s concurrency limit into the same five-attempt retry loop we use for HxRun launches: when capacity is saturated the job logs a retry, waits 120 s, and after five tries it is treated as failed and rescheduled to its next interval (`backend/services/scheduling/scheduler_engine.py`).
- When a schedule is deleted we now persist its name/path snapshot with every archived execution so Execution History keeps the original experiment label instead of dropping to “Archived Schedule” (`backend/api/scheduling.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`, `backend/services/scheduling/scheduler_engine.py`).

## 2025-10-17 Scheduling Failure Handling Refresh

- Removed the legacy `failed_execution_count` bookkeeping and now rely on HxRun launch retries alone; each scheduled occurrence attempts to start the robot up to five times before reporting failure (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/experiment_executor.py`).
- When a run aborts, the scheduler marks the schedule inactive via manual recovery and emails the configured contacts using the existing notification pipeline (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/sqlite_database.py`).
- Non-abort launch failures now trigger an “execution_failed” notification so operators are alerted even when the robot never started (`backend/services/scheduling/scheduler_engine.py`).
- Introduced an `archived` flag for schedules, API support to list/archive/unarchive them, and a dedicated frontend tab so operators can review retired experiments without cluttering the active list (`backend/models.py`, `backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/components/ScheduleList.tsx`, `frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-17 Schedule Deletion Concurrency Fix

- Background scheduler updates now avoid touching the `updated_at` field by passing `touch_updated_at=False` whenever they persist interval/next-run metadata. This keeps optimistic locking tokens stable for UI operations (`backend/services/scheduling/scheduler_engine.py`, `backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Added a `touch_updated_at` flag through the scheduling data layer so API writes still bump timestamps while automated maintenance writes do not, preserving multi-user safeguards without spurious 409s on delete requests (`backend/services/scheduling/database_manager.py`, `backend/services/scheduling/sqlite_database.py`).
- Updated the scheduler manual-recovery test stub to support the new signature (`backend/tests/test_scheduler_manual_recovery.py`).
- Experiment execution now resolves stored relative experiment paths against the Hamilton `Methods` root, so imports from “Active Experiment” (and other sibling folders) run without falling back to the legacy LabProtocols directory (`backend/services/scheduling/experiment_executor.py`).
- Scheduling API writes now persist the exact `updated_at` values supplied by the caller instead of relying on SQLite’s UTC `CURRENT_TIMESTAMP`, eliminating timezone drift between optimistic-lock headers and stored records (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `backend/models.py`).
- Manual recovery helpers write explicit UTC timestamps to keep schedule metadata consistent with other updates (`backend/services/scheduling/sqlite_database.py`).

## 2025-10-16 Tray Menu Simplification & Log History Relocation

- Replaced the Windows tray menu with the three requested actions so the icon only exposes `Open in Browser`, `Show Data`, and `Terminate` (`backend/utils/system_tray.py`); terminate still runs the graceful stop callback before forcing the process down.
- Logging setup now writes rotated archives into `data/logs/history`, keeps only the active-day aliases in `data/logs`, and moves existing dated `.log`/`.log.gz` files into the history folder during startup (`backend/utils/logging_setup.py`).

## 2025-10-15 README Completion

- Filled the missing sections in `README.md` to align with project conventions: completed Implemented Modules for SQL Server, Camera, and Scheduling; and added a concise Local Development guide.
- Documented key API groups and data paths, included an example `backend/.env` snippet, and called out the Microsoft ODBC driver requirement for SQL Server connectivity.
- Kept existing highlights, repository layout, and Windows packaging steps; no code changes required.

## 2025-10-15 Database Browser Layout Tuning

- Limited the database browser cards to responsive `maxHeight` values and contained overflow so table content scrolls inside the card instead of stretching past the viewport on mobile (`frontend/src/pages/DatabasePage.tsx`).
- Reworked the table container to keep pagination anchored below the scroll area and moved filter editors into a responsive drawer so the data grid keeps its height even with multiple conditions (`frontend/src/components/DatabaseTable.tsx`).
- Increased the responsive height allowances for the database cards and enforced larger minimum table heights so roughly 10 rows remain visible on desktop and more rows show on mobile even when chips are present (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).

## 2025-10-14 Branding Refresh

- Renamed all user-facing strings, documentation, environment defaults, and packaging assets from “PyRobot” to “RobotControl” (`README.md`, `backend/main.py`, `frontend/src/**/*`, `build_scripts/*`, `RobotControl.spec`, etc.).
- Updated environment variable prefixes to `ROBOTCONTROL_` and adjusted default credentials/subjects accordingly (`backend/services/auth.py`, `.env.example`, `backend/services/notifications.py`).
- Regenerated packaging spec as `RobotControl.spec` with relative project paths so branding stays consistent without hard-coded directories.
- Cleaned up scheduling/monitoring UI copy, removed the discovery auto-scan, limited folder imports to localhost, trimmed summary cards, and simplified system-status widgets (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/scheduling/FolderImportDialog.tsx`, `frontend/src/pages/MonitoringPage.tsx`, `frontend/src/components/MonitoringDashboard.tsx`, `frontend/src/App.tsx`).
- Formatted archive video labels to display friendly timestamps while keeping actions accessible on mobile (`frontend/src/components/camera/VideoArchiveTab.tsx`).
- Refined the top navigation bar layout so the title, user info, and buttons wrap cleanly on small screens (`frontend/src/App.tsx`).
- Widened the database browser layout so the table list keeps its refresh button and the data card/pagination stay fully visible even with multiple filters (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).

## 2025-10-14 Camera Page Streamlining

- Camera page now focuses on two tabs (Archive + Live Streaming); dropped the inline system-status modal and live camera grid so health info stays on the dedicated System Status screen (`frontend/src/pages/CameraPage.tsx:392-760`).
- Streaming panel shows only session ID and connection state while keeping fullscreen playback support; removed quality/bandwidth/FPS details per UX request (`frontend/src/pages/CameraPage.tsx:660-750`).
- Video archive folders/files wrap cleanly on mobile and always expose action buttons thanks to responsive tweaks and loading spinners (`frontend/src/components/camera/VideoArchiveTab.tsx:200-464`).

## 2025-10-14 Scheduling Recovery Reference & Camera Notes

- Interval miss grace is half the configured interval hours; see `backend/services/scheduling/scheduler_engine.py:575-599` where `_find_due_jobs` computes `grace_period_minutes = (experiment.interval_hours * 60) / 2`.
- Missed runs log `start_time` plus the current timestamp as `end_time`, so execution history shows a long `calculated_duration_minutes`; originates in `_find_due_jobs` (`backend/services/scheduling/scheduler_engine.py:583-599`) and the formatter `get_execution_history` (`backend/services/scheduling/sqlite_database.py:1399-1424`).
- New pre-execution steps register via `_register_builtin_steps` (`backend/services/scheduling/pre_execution.py:103-160`); implement handlers with cleanup similar to `_scheduled_to_run_step`.

## 2025-10-13 Admin User Controls

- Limited the admin API to user email updates and account deletion, adding dedicated endpoints while preventing self-deletion and duplicate email assignment (`backend/api/admin.py`, `backend/services/auth.py`, `backend/services/auth_database.py`).
- Simplified the admin UI to match: user management now supports only editing email addresses or removing accounts, with refreshed UX feedback (`frontend/src/components/UserManagement.tsx`, `frontend/src/pages/AdminPage.tsx`, `frontend/src/services/api.ts`).

## 2025-10-13 Dashboard & Layout Cleanup

- Removed descriptive footer panels from Scheduling and Backup pages to keep the UI focused on actionable controls (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/pages/BackupPage.tsx`).
- Centered About page cards and ensured they stretch evenly by flexing grid items, eliminating the right-leaning layout (`frontend/src/pages/AboutPage.tsx`).
- Streamlined the Dashboard by dropping the Quick Actions card and centering the experiment widget; the latest experiment panel now loads after a 1 s handshake instead of 3 s (`frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ExperimentStatus.tsx`).

## 2025-10-13 Multi-User Concurrency & Token Refresh

- Added optimistic concurrency to schedule update/delete/manual-recovery routes using `If-Unmodified-Since` tokens from the UI; stale submissions now raise HTTP 409 and trigger an automatic reload (`backend/api/scheduling.py`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/types/scheduling.ts`).
- Scheduler now exposes `invalidate_schedule` and returns the manual-recovery snapshot as part of `/status/scheduler`, keeping the cache encapsulated and the recovery banner in sync with the 30 s poll (`backend/services/scheduling/scheduler_engine.py`, `frontend/src/hooks/useScheduling.ts`).
- Axios interceptors retry once with the stored refresh token before logging out, and a custom event keeps `AuthContext` aligned when a new access token is issued (`frontend/src/services/api.ts`, `frontend/src/context/AuthContext.tsx`).

## 2025-10-13 Multiline Alert Rendering & Status Dialogs

- Normalized newline handling so backend strings containing `\n` render as real line breaks in shared alerts and restore status dialogs via the new `normalizeMultilineText` helper (`frontend/src/components/ErrorAlert.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/text.ts`).
- Added a reusable `StatusDialog` wrapper to keep success/error feedback consistent on mobile and migrated the scheduling admin panels (`NotificationEmailSettingsPanel`, `NotificationContactsPanel`, `ImprovedScheduleForm`, and `DatabaseRestore`) to use it (`frontend/src/components/StatusDialog.tsx`, `frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/components/scheduling/ImprovedScheduleForm.tsx`).
- Scheduler delete now falls back to the SQLite manager when the in-memory engine isn't loaded, so admins can remove schedules even if the scheduler service is offline (`backend/api/scheduling.py`).
- Database restore kicks off a health-check watcher that clears maintenance mode as soon as the backend responds again instead of waiting the full sixty-second timeout (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-13 Camera Archive Virtualization

- Replaced the archive card-grid with a collapsible tree that virtualizes video rows via `react-window`; per-folder state now lives inside `VideoArchiveTab` and supports optional lazy loading (`frontend/src/components/camera/VideoArchiveTab.tsx`, `frontend/src/types/components.ts`).
- Updated the camera page to consume the shared archive component so the optimized UI appears on the main route (`frontend/src/pages/CameraPage.tsx`).
- Added a full-screen dialog for the live streaming preview triggered from the inline player, closing automatically if the session drops (`frontend/src/pages/CameraPage.tsx`).
- Standardised SQL backup writes to `data/backups` and removed the compressed backup attempt so Express Edition uses the same reliable sqlcmd path as the legacy UI (`backend/config.py`, `backend/services/backup.py`).

## 2025-10-13 Persistent Auth Rework

- Replaced the in-memory AuthService with a SQLite-backed store (`backend/services/auth.py`, `backend/services/auth_database.py`) seeded with `admin / ShouGroupAdmin`, introduced hashed refresh-token tracking, registration, change-password, and admin reset flows (`backend/api/auth.py`, `backend/api/admin.py`, `backend/scripts/auth_cli.py`).
- Added regression tests for the new flows (`backend/tests/test_auth.py`) and CLI helpers for operators; note pytest is required to run the suite.
- Updated the React client with self-serve registration, change-password dialog, and refreshed auth context (`frontend/src/context/AuthContext.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/components/ChangePasswordDialog.tsx`, `frontend/src/App.tsx`, `frontend/src/services/api.ts`).
- Introduced password reset request queue + admin tooling and forgot-password UI (`backend/api/auth.py`, `backend/api/admin.py`, `frontend/src/components/UserManagement.tsx`, `frontend/src/pages/LoginPage.tsx`).
- Hardened live streaming session tracking so stale sessions no longer block new users (`backend/services/live_streaming.py`).
- Tweaked Monitoring page to avoid duplicate headings and hide experiment card in the detail view (`frontend/src/pages/MonitoringPage.tsx`, `frontend/src/components/SystemStatus.tsx`).
- Restored a lightweight `/admin` console that surfaces the new user management tooling and hides non-admin routes (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/pages/AdminPage.tsx`).

## 2025-10-12 Maintenance UX & Modal Alerts

- Added centralized maintenance tracking so destructive workflows (e.g. database restore) trigger a short-lived maintenance window that pauses API polling, surfaces a countdown dialog, and resumes once the backend is reachable (`frontend/src/utils/MaintenanceManager.ts`, `frontend/src/hooks/useMaintenanceMode.ts`, `frontend/src/services/api.ts`).
- Refresh Flow: Database restore confirmations now show a dedicated modal summarizing the operation impact and, on success/failure, follow-up pop-up dialogs ensure mobile users see status immediately (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/components/MaintenanceDialog.tsx`).
- Next session: migrate other admin/scheduling pages to reuse the shared pop-up dialog pattern so error/success feedback is consistent across desktop and mobile.

## 2025-10-12 Connection Locality Detection

- Added `backend/utils/network_utils.py` and `backend/api/dependencies.py` so endpoints can classify requests as local vs remote using IP heuristics. Auth endpoints now attach session locality metadata to login and `/api/auth/me` responses for the frontend to consume.
- Locked down `/api/backup/restore` to local callers via the new dependency and emit structured audit events for restore attempts (`backend/api/backup.py`, `backend/utils/audit.py`). Locality now means loopback-only (127.0.0.1/::1).
- Restricted `/api/database/execute-procedure` to loopback connections, logging every invocation (or error) with the initiating user for audit purposes (`backend/api/database.py`). Deferred: extend checks to additional write endpoints, bubble locality flags into the frontend to hide destructive UI, and surface audit history.
- Scheduling mutations are now loopback-only: create, update, delete, manual recovery, and notification management endpoints depend on the locality guard and emit audit entries (`backend/api/scheduling.py`). Remaining UI work: hide restricted controls when the session is remote.
- Backup creation/deletion and database cache clearing require a loopback connection and log every attempt (`backend/api/backup.py`, `backend/api/database.py`).
- Added modal status dialogs for backup create/restore flows and introduced a maintenance window gate that pauses background API calls and surfaces a countdown dialog after restores (`frontend/src/components/DatabaseRestore.tsx`, `frontend/src/utils/MaintenanceManager.ts`, `frontend/src/components/MaintenanceDialog.tsx`, `frontend/src/services/api.ts`).
- Corrected the restore warning copy so bullet points render properly in the confirmation banner (`frontend/src/components/DatabaseRestore.tsx`).

## 2025-10-12 Performance Logging Cleanup

- Removed the unused performance logging subsystem (router, middleware, utilities) so the backend stops emitting empty `performance_*.log` files (`backend/api/performance.py`, `backend/middleware/performance.py`, `backend/utils/logger.py`, `backend/main.py`).

## 2025-10-12 Backup Path Persistence

- Pointed the backup service at the managed data directory so PyInstaller builds persist backups beside `RobotControl.exe` rather than the temp `_MEI` unpack location (`backend/services/backup.py`).

## 2025-10-11 Manual Recovery Dropdown

- Swapped the manual recovery recipient text area for a multi-select fed by Notification Contacts, keeping custom addresses visible and clarifying the helper copy (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Passed the contact list through to the email settings panel so selections stay synchronized with the scheduler contact management view (`frontend/src/pages/SchedulingPage.tsx`).

## 2025-10-11 Manual Recovery Distribution

- Manual recovery recipient lists persist in NotificationSettings and flow through the admin API/UI; legacy `ROBOTCONTROL_*` email fallbacks were removed so delivery now depends on stored configuration (`backend/api/scheduling.py`, `backend/services/scheduling/sqlite_database.py`, `backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Hamilton TRC attachments convert to `.log` files with predictable names before mailing, and scheduler alerts prefer the configured distribution list when present (`backend/services/notifications.py`, `backend/tests/test_notifications.py`).
- Restored missing FastAPI imports so the scheduling router initializes correctly in packaged builds (`backend/api/scheduling.py`); rebuilt frontend assets, refreshed embedded resources, and regenerated the PyInstaller executable to capture all changes (`frontend build output`, `backend/embedded_static.py`, `dist/RobotControl.exe` via `build_scripts/pyinstaller_build.py`).

## 2025-10-10 Long-Run Alerts & SMTP Test Harness

- Scheduler watchdog now fires long-running alerts strictly at 2x the estimated duration and falls back to a stitched MP4 summary built from the latest three rolling clips (recorded at 7.5 fps) when no experiment archive exists (`backend/services/notifications.py`, `backend/services/scheduling/scheduler_engine.py`, `backend/tests/test_notifications.py`).
- Camera recorder targets 7.5 fps for rolling clips and the unit suite asserts the new writer configuration (`backend/services/camera.py`, `backend/tests/test_camera.py`).
- Added `/api/scheduling/notifications/settings/test`, UI wiring, and build safeguards: Send Test Email button, hook integration, and preserved `dist/data/backups` during PyInstaller rebuilds (`backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/services/schedulingApi.ts`, `frontend/src/hooks/useScheduling.ts`, `frontend/src/pages/SchedulingPage.tsx`, `build_scripts/pyinstaller_build.py`).

## 2025-10-10 SMTP Config Panel

- Swapped Fernet secrets for Windows DPAPI so SMTP credentials encrypt/decrypt without a shared key (`backend/utils/secret_cipher.py`, `backend/services/notifications.py`).
- Added NotificationSettings persistence + admin API and extended the scheduling UI with an Email Settings tab (DPAPI-backed password storage) (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`).
- Added encrypted NotificationSettings storage and admin API so the scheduler reads SMTP host/sender/password from SQLite instead of environment variables (`backend/services/scheduling/sqlite_database.py`, `backend/api/scheduling.py`, `backend/services/notifications.py`).
- Extended the scheduling admin UI with an Email Settings tab that encrypts passwords via Fernet and guides operators through key setup (`frontend/src/components/scheduling/NotificationEmailSettingsPanel.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).

## 2025-10-10 Scheduler SQLite Def Fix

- Removed the duplicated, truncated `_row_to_scheduled_experiment` helper that left a dangling try block and broke PyInstaller execution (`backend/services/scheduling/sqlite_database.py`).
- Verified the corrected module via `python -m compileall backend/services/scheduling/sqlite_database.py` to ensure the packaged build loads cleanly.

## 2025-10-09 Scheduler Watchdog & Admin Notifications

- Implemented long-running and abort alert dispatch with notification logging, attachment bundling, and contact cache refresh (`backend/services/scheduling/scheduler_engine.py`, `backend/services/notifications.py`, `backend/services/scheduling/sqlite_database.py`).
- Added admin-facing notifications tab with contact CRUD, filterable delivery history, and surfaced latest alert status on schedule detail cards (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/scheduling/NotificationContactsPanel.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Extended schedule form to select contacts and wired notification log API plus persistence helpers; added backend tests covering notification logging CRUD (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `backend/api/scheduling.py`, `backend/tests/test_notification_logging.py`).

## 2025-10-09 Notification Contact Cache Bridge

- Added scheduling database-manager wrappers for contact CRUD so API and future services reuse the same SQLite helpers and keep timestamps aligned (`backend/services/scheduling/database_manager.py`).
- Scheduler now caches notification contacts and refreshes them on demand for upcoming alert logic (`backend/services/scheduling/scheduler_engine.py`).
- Contact management API endpoints trigger a cache refresh after create/update/delete operations to keep the engine in sync (`backend/api/scheduling.py`).

## 2025-10-09 Scheduling TZ & Video Archive Adjustments

- Normalized scheduling ISO timestamps to local naive datetimes so non-UTC systems no longer see start-time drift (`backend/utils/datetime.py`, `backend/api/scheduling.py`, `backend/models.py`, `backend/services/scheduling/*`, `backend/services/experiment_monitor.py`).
- Routed experiment archiving through StorageManager to keep original one-minute clips and surface richer metadata to automation (`backend/services/camera.py`, `backend/services/automatic_recording.py`, `backend/tests/test_camera.py`).
- Resolved PyInstaller data paths so packaged builds read/write the real data/videos directory beside the executable (`backend/config.py`).

## 2025-10-09 Camera Resolution ASCII Fix

- Replaced the multiplication symbol in camera resolution displays and fullscreen hint with ASCII `x` so Windows clients no longer see kanji U+8133 (Japanese "brain") in place of the separator (`frontend/src/pages/CameraPage.tsx`, `frontend/src/components/CameraViewer.tsx`).

## 2025-10-08 Streaming Guard & UI Polish (Binary Refresh)

- Refined the streaming CPU guard to sample the RobotControl process with a rolling window, preventing false "CPU limit reached" shutdowns while keeping the soft/hard protections (`backend/services/live_streaming.py`).
- Widened scheduling layout padding so desktop cards and calendars no longer hug the container edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now includes a short schedule-id suffix to distinguish duplicate method names (`frontend/src/components/ExecutionHistory.tsx`).
- Restored the lightweight camera live-stream view without frame counters while retaining start/stop controls (`frontend/src/pages/CameraPage.tsx`).
- Rebuilt the frontend, re-embedded static assets, and produced a fresh PyInstaller binary with the updated bundle (`build_scripts/embed_resources.py`, `build_scripts/pyinstaller_build.py`, `dist/RobotControl.exe`).

## 2025-10-08 Streaming Guard & Scheduling Polish

- Reworked the streaming CPU guard to sample the RobotControl process, smooth spikes, and require consecutive hits before terminating sessions (`backend/services/live_streaming.py`).
- Widened scheduling tab padding and card content so laptop layouts breathe instead of hugging the edges (`frontend/src/pages/SchedulingPage.tsx`).
- Execution history's experiment filter now shows each schedule's short id alongside the name to avoid duplicate labels (`frontend/src/components/ExecutionHistory.tsx`).

## 2025-10-08 Scheduling Layout & Streaming Consolidation

- Reordered top-level navigation so System Status sits beside About, updating both the desktop tabs and mobile drawer (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`).
- Relaxed the scheduling page spacing with wider gutters, roomier tabs, and padded cards while keeping manual recovery and calendar content consistent (`frontend/src/pages/SchedulingPage.tsx`, `frontend/src/components/ScheduleList.tsx`).
- Extended monitoring data to carry streaming status and reliable timestamps, then surfaced the service metrics on the System Status dashboard (`frontend/src/hooks/useMonitoring.ts`, `frontend/src/components/SystemStatus.tsx`, `frontend/src/components/MonitoringDashboard.tsx`).
- Streamlined the Camera streaming tab to just session controls, removing the metrics card and video preview while keeping start/stop flows intact (`frontend/src/pages/CameraPage.tsx`).

## 2025-10-08 Monitoring & Scheduling Tweaks

- Refined the scheduling form so the improved modal now powers both create and edit flows, requires an explicit experiment prep option, and removes the unused Hamilton tables flag (`frontend/src/components/scheduling/ImprovedScheduleForm.tsx`, `frontend/src/pages/SchedulingPage.tsx`, `frontend/src/hooks/useScheduling.ts`).
- Mobile monitoring header now wraps cleanly, simplifies the status chip, and keeps last-update info readable at small widths (`frontend/src/components/MonitoringDashboard.tsx`).
- Latest bundle embedded and PyInstaller binary refreshed after UI fixes (`backend/embedded_static.py`).

## 2025-10-08 Navigation & Mobile Polish

- Database tables lose the nested scroll on phones by relaxing the card height on `DatabasePage` and only constraining `TableContainer` on md+ breakpoints so pagination stays in view (`frontend/src/pages/DatabasePage.tsx`, `frontend/src/components/DatabaseTable.tsx`).
- Removed the unused Admin surface, renamed Monitoring to System Status, and introduced a dedicated About page with navigation hooks across tabs, the mobile drawer, breadcrumbs, and keyboard shortcuts (`frontend/src/App.tsx`, `frontend/src/components/MobileDrawer.tsx`, `frontend/src/components/NavigationBreadcrumbs.tsx`, `frontend/src/hooks/useKeyboardNavigation.ts`, `frontend/src/components/KeyboardShortcutsHelp.tsx`, `frontend/src/pages/AboutPage.tsx`).
- Compact experiment summaries now wrap their header/status controls and stack timestamps on narrow widths, avoiding truncated chips and timestamps (`frontend/src/components/ExperimentStatus.tsx`).
- Dashboard quick actions point at the new System Status route and expose a shortcut to the About page while retiring the redundant system info card (`frontend/src/pages/Dashboard.tsx`).
- Added a PyInstaller runtime hook that filters the deprecated `pkg_resources` warning so packaged binaries start cleanly, and wired it into the spec (`build_scripts/runtime_hooks/silence_pkg_resources_warning.py`, `Py
