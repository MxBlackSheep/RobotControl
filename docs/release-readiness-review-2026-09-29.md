# RobotControl — pre-feature release-readiness review (29 Sep 2026)

**Scope:** every change from tag `V0.1.4` (24 Feb 2026) to local `main` `5aed710` (28 Sep 2026): 54 commits, 289 files, +31,179 / −12,670 lines. Reviewed from a reconstruction of the lab PC's Git history plus a working-tree comparison.

**Limits:** I could not run the backend or frontend test suites. This environment has no Python 3.14.7, and the package registries blocked the installs. The findings below come from reading the code, a static lint of the changed Python (ruff) and the project's own verification records. I did not exercise any hardware.

## Verdict

The code quality is high and the safety thinking is careful. The biggest risk is not a single bug. Seven months of robot-facing changes have not been released, are not fully backed up, and are not accepted on hardware. Fix the items under "Must fix" before starting new features.

## Action status

Update this table as items close; it also tracks open findings from the 26–27 September reviews.

| # | Item | Status |
| --- | --- | --- |
| 1 | Back up unpushed commits | Done 29 Sep: branch `backup/2026-09-29` on GitHub |
| 2 | One release candidate | Built 29 Sep as 0.1.5 in `dist/`; tag `V0.1.5` only after owner confirmation; record which build the robot PC runs |
| 3 | Hardware acceptance gates | Open, needs lab owner |
| 4 | Stalled status request never recovers | Fixed 29 Sep: 20 s request deadline, browser-verified |
| 5 | Stale tests | Done 29 Sep: backend 308 and unit 78 pass; 9 outdated browser cases removed (package authoring, report wizard, tool authoring have no browser check) |
| 6 | Operation scripts hold scheduler locks | Open: needs a design decision (subprocess with limit) |
| 7 | Single version source | Done 29 Sep: `backend/version.py`, 0.1.5 |
| 8 | Scope decision on database tooling / package v1 | Open, product decision |
| 9 | Unsandboxed Python warning in UI | Open |
| 10 | Unanchored `.gitignore` patterns | Done 29 Sep |
| — | Restores do not check for an active robot run | Open, behavior change to decide |
| — | Camera five-second delivery cutoff ([remote review](remote-connection-review-2026-09-26.md)) | Open, not reproduced |
| — | Whole-app layout and dark mode ([frontend UI review](frontend-ui-review-2026-09-26.md)) | Proposal, not scheduled |

Correction to item 6: `database_change_guard()` refuses while a run is active or the robot is present, so a stuck script cannot stall a running method. It delays the next dispatch and anything waiting on the scheduler locks.

## Must fix before new features

1. **31 commits exist only on the lab PC.** GitHub `main` stops at `cd4d908` (17 Sep). The later ~18.7k lines (database tools, report wizard, labware redesign, scheduling lab integration) have one copy, on one disk. **Action:** push now, on a branch if `main` is not ready.
2. **There is no single release candidate.** `dist/` holds six parallel candidates named after features (`database-access-…`, `tool-publishing-…` and others). None is tagged, and it is unclear which one runs on the robot PC. **Action:** pick one commit, tag it `v0.2.0-rc1` (or similar), build once and record which build is deployed.
3. **Hardware acceptance is still open for robot-facing changes.** These come from the project's own notes:
   - Scheduling lab integration: "A supervised deployed-method comparison is still required before hardware use."
   - Camera recovery: physical unplug/replug, multiple devices, remote viewing while recording, and endurance.
   - Performance: N100 real workload, the 24-hour screen and the 10-day endurance run.

   **Action:** make these explicit release gates with owners, or scope the release so it excludes them.
4. **A confirmed defect is unfixed and documented only in uncommitted files.** When a status request stalls, System Status never recovers. It stays "connected" and Refresh stays disabled (reproduced for 99 s). `useSerialPolling` has no request deadline, and camera control polling uses the same hook. The finding lives in the untracked `docs/remote-connection-review-2026-09-26.md` and an unstaged edit to `polling-maintenance-guide.md`. **Action:** commit both files and add a request timeout with abort-and-retry. This is a small fix.
5. **The test suite is knowingly red.** Twelve backend tests fail and were accepted as "pre-existing". Eleven of them assume forwarded-localhost headers grant local access, which the new security fix correctly removed, so those tests are stale. With a red baseline, a new regression cannot be seen. **Action:** update or delete the stale tests so that green means green.
6. **Database operation scripts can freeze the scheduler.** `DatabaseTools.preview()` and `.execute()` run uploaded operation Python inside the server process. While they run, they hold `database_change_guard()`, which takes the scheduler's `_schedules_lock` and `_jobs_lock`. A slow SQL statement (30 s timeout each) or a stuck script stalls dispatch, the status API and recovery actions until it returns. Reports already run in a subprocess with a 5-minute limit; operations do not. **Action:** give operations the same subprocess and time limit, or hold the guard only for the final state check. The guard's own docstring says "short transaction."

## Should fix

7. **Version identity is inconsistent.** `pyproject.toml` says 1.0.0, `package.json` says 2.0.0, and the tags are `v0.1.0`, then `V0.1.1`–`V0.1.4`. V0.1.1 and V0.1.2 point to the same commit. Use one version source and show it in the UI and logs so support can tell what is running.
8. **Scope drift toward a database-tooling platform.** Roughly 30 of the last 54 commits build package, report and tool authoring: two package contract versions, Python tool authoring, SQL read-only account provisioning and the report wizard. The package contract already has v1 and v2 before any release. Decide whether this is core to running directed-evolution experiments. If no external v1 packages exist, drop v1 now.
9. **Uploaded Python is unsandboxed.** This is documented and deliberate, and it is limited to local admins. Make it explicit in the Add tool UI ("runs with RobotControl's permissions on this PC") and in the release notes.
10. **Unanchored `.gitignore` patterns.** `main.py`, `tools/` and `*.spec` match at any depth. A new `something/main.py` or `tools/` folder would be silently excluded from Git.

## Hygiene (low)

- Ruff on the changed Python: about 50 unused imports and 3 unused variables (for example `api/scheduling.py:1397`, `api/system.py:168`), plus a duplicate `threading` import in `services/monitoring.py:384`. The SQL string-building warnings I checked are safe: they use identifiers from quoted or whitelisted sources and integer casts.
- The audit log records the `X-Forwarded-For` value as the client IP. The access decision correctly uses the socket peer, but the logged IP can be spoofed. Log both.
- Documentation sprawl: `implementation-notes.md` is 120 KB, there are four dated review documents, and `recovery/` holds about 30 evidence folders outside Git. Consider one changelog per release plus the maintenance guides.

## What's good

- Remote callers can no longer gain "local" access through `X-Forwarded-For`, and Uvicorn proxy headers are off.
- SQL passwords are encrypted with DPAPI. The read-only account setup never alters existing logins and cleans up on failure.
- Destructive operations have a preview, a typed confirmation, a snapshot re-check, an idempotent receipt journal and an audit trail.
- The launch guard re-checks recovery, maintenance and HxRun state and makes a durable write before `Popen`. Report execution runs in a separate process with size and time limits.
- There is no debug logging, no TODO or FIXME, and no secrets in the diff.

## Suggested order

Push (1) → commit the docs and fix the polling timeout (4) → make the tests green (5) → isolate operations (6) → tag one RC (2, 7) → hardware acceptance (3) → release → then new features.
