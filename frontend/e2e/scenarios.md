# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Restore request outlives the shared 10 s API timeout (`fix/restore-request-timeout`)

- A restore that succeeds after more than 10 s is reported as "Restore Failed:
  Request timed out" because the restore call still uses the shared 10 s limit.
- The longer limit is applied to the shared client, so every other request (lists,
  health checks, polling) waits minutes instead of 10 s before reporting a stall.
- The restore limit is shorter than the backend's `RESTORE_TIMEOUT` (600 s), so the
  browser gives up while the server is still restoring and shows a false failure.
- The restore limit is unbounded, so a restore request whose server never answers
  leaves the dialog on "Restoring..." forever with no message.
- While a long restore is in progress, the Restore and Cancel buttons become usable
  again and a second restore can be sent.
