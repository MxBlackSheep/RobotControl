# Operations redesign failure scenarios

Written before the operations redesign implementation.

- Selecting a schedule on a phone leaves its actions below the whole list, loses list position on Back, or loses selection during resize.
- Queue/recovery state disappears behind selected details; remote users gain mutation controls; recovery-required schedules can be deleted or archived.
- The schedule editor overflows a phone, hides important configured values in accordions, discards drafts on Escape, or loses draft fields after a failed save.
- History, notification, or method tables widen the page; filters vanish when switching sections; hidden retained history continues polling.
- Archive file names/actions collide because fixed-height virtual rows wrap; opening a folder leaves repeated nested scroll areas; Back loses the selected folder.
- Camera layout changes reconnect streaming or issue recording/hardware mutations; status and keyboard close become inaccessible.

Repeatable evidence: run `npx playwright test operations.spec.ts camera.spec.ts` against the built frontend. Operations tests intercept only isolated browser API requests. Screenshots, traces and mutation assertions are retained in `recovery/viewer-verification`.
